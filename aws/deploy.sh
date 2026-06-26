#!/usr/bin/env bash
# Deploy SharePoint -> Splunk Lambda to splk-pmops-dev-1 (676878928498)
# Includes: daily EventBridge schedule, S3 date-partitioned snapshots,
#           DynamoDB change-tracking table.
set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
AWS_PROFILE="splk-pmops-dev-1_splkcld_account_admin"
AWS_REGION="us-east-1"
AWS_ACCOUNT="676878928498"

FUNCTION_NAME="sharepoint-compliance-sync"
LAMBDA_ROLE_NAME="sharepoint-compliance-lambda-role"
SECRET_PREFIX="sharepoint-compliance"

# Daily at 6 AM UTC
SCHEDULE_EXPRESSION="cron(0 6 * * ? *)"
RULE_NAME="${FUNCTION_NAME}-daily"
OLD_RULE_NAME="${FUNCTION_NAME}-hourly"   # remove if it still exists

# S3 bucket for compliance data (separate from Lambda package bucket)
S3_DATA_BUCKET="sharepoint-compliance-data-${AWS_ACCOUNT}"

# DynamoDB table for status-change tracking
DYNAMODB_TABLE="sharepoint-compliance-changes"

# DynamoDB table for achievement history (roadmap -> compliant transitions)
ACHIEVEMENTS_TABLE="sharepoint-compliance-achievements"

# Secrets (read from local .env)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: .env not found at $ENV_FILE"
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

: "${SHAREPOINT_CLIENT_ID:?SHAREPOINT_CLIENT_ID not set in .env}"
: "${SHAREPOINT_CLIENT_SECRET:?SHAREPOINT_CLIENT_SECRET not set in .env}"
: "${SHAREPOINT_TENANT_ID:?SHAREPOINT_TENANT_ID not set in .env}"
: "${SPLUNK_HEC_TOKEN:?SPLUNK_HEC_TOKEN not set in .env}"
: "${SPLUNK_INDEX:?SPLUNK_INDEX not set in .env}"

HEC_URL="https://http-inputs-products-telemetry.splunkcloud.com:443/services/collector/event"

export AWS_PROFILE AWS_REGION

echo "================================================================"
echo "Deploying SharePoint -> Splunk Lambda"
echo "  Account   : $AWS_ACCOUNT"
echo "  Region    : $AWS_REGION"
echo "  Profile   : $AWS_PROFILE"
echo "  Function  : $FUNCTION_NAME"
echo "  Schedule  : $SCHEDULE_EXPRESSION"
echo "  S3 data   : $S3_DATA_BUCKET"
echo "  DynamoDB  : $DYNAMODB_TABLE"
echo "================================================================"

# ---------------------------------------------------------------------------
# 1. Verify AWS auth
# ---------------------------------------------------------------------------
echo -e "\n[1/9] Verifying AWS credentials..."
CALLER=$(aws sts get-caller-identity --output json)
echo "  Authenticated as: $(echo "$CALLER" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['Arn'])")"

# ---------------------------------------------------------------------------
# 2. Create IAM role + policies (idempotent)
# ---------------------------------------------------------------------------
echo -e "\n[2/9] Setting up IAM role..."
TRUST_POLICY='{
  "Version":"2012-10-17",
  "Statement":[{
    "Effect":"Allow",
    "Principal":{"Service":"lambda.amazonaws.com"},
    "Action":"sts:AssumeRole"
  }]
}'

ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT}:role/${LAMBDA_ROLE_NAME}"
if aws iam get-role --role-name "$LAMBDA_ROLE_NAME" &>/dev/null; then
  echo "  IAM role already exists"
else
  aws iam create-role \
    --role-name "$LAMBDA_ROLE_NAME" \
    --assume-role-policy-document "$TRUST_POLICY" \
    --description "Lambda execution role for SharePoint compliance sync" \
    --output json > /dev/null
  echo "  IAM role created"
fi

# Managed policies
for POLICY in \
  "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole" \
  "arn:aws:iam::aws:policy/SecretsManagerReadWrite"; do
  aws iam attach-role-policy --role-name "$LAMBDA_ROLE_NAME" --policy-arn "$POLICY" 2>/dev/null || true
done

# Inline policy for S3 data bucket + DynamoDB changes table
DATA_POLICY="{
  \"Version\": \"2012-10-17\",
  \"Statement\": [
    {
      \"Sid\": \"S3ComplianceData\",
      \"Effect\": \"Allow\",
      \"Action\": [\"s3:PutObject\", \"s3:GetObject\", \"s3:ListBucket\"],
      \"Resource\": [
        \"arn:aws:s3:::${S3_DATA_BUCKET}\",
        \"arn:aws:s3:::${S3_DATA_BUCKET}/*\"
      ]
    },
    {
      \"Sid\": \"DynamoDBChanges\",
      \"Effect\": \"Allow\",
      \"Action\": [
        \"dynamodb:PutItem\",
        \"dynamodb:BatchWriteItem\",
        \"dynamodb:Query\",
        \"dynamodb:GetItem\"
      ],
      \"Resource\": [
        \"arn:aws:dynamodb:${AWS_REGION}:${AWS_ACCOUNT}:table/${DYNAMODB_TABLE}\",
        \"arn:aws:dynamodb:${AWS_REGION}:${AWS_ACCOUNT}:table/${DYNAMODB_TABLE}/index/*\",
        \"arn:aws:dynamodb:${AWS_REGION}:${AWS_ACCOUNT}:table/${ACHIEVEMENTS_TABLE}\",
        \"arn:aws:dynamodb:${AWS_REGION}:${AWS_ACCOUNT}:table/${ACHIEVEMENTS_TABLE}/index/*\"
      ]
    }
  ]
}"

aws iam put-role-policy \
  --role-name "$LAMBDA_ROLE_NAME" \
  --policy-name "sharepoint-compliance-data-access" \
  --policy-document "$DATA_POLICY" \
  --output json > /dev/null
echo "  Policies attached (managed + inline)"

# ---------------------------------------------------------------------------
# 3. Store secrets (idempotent)
# ---------------------------------------------------------------------------
echo -e "\n[3/9] Storing secrets in Secrets Manager..."

store_secret() {
  local name="$1" value="$2"
  if aws secretsmanager describe-secret --secret-id "$name" &>/dev/null; then
    aws secretsmanager put-secret-value --secret-id "$name" --secret-string "$value" --output json > /dev/null
    echo "  Updated: $name"
  else
    aws secretsmanager create-secret --name "$name" --secret-string "$value" \
      --description "SharePoint compliance sync secret" --output json > /dev/null
    echo "  Created: $name"
  fi
}

store_secret "${SECRET_PREFIX}-client-id"     "$SHAREPOINT_CLIENT_ID"
store_secret "${SECRET_PREFIX}-client-secret" "$SHAREPOINT_CLIENT_SECRET"
store_secret "${SECRET_PREFIX}-tenant-id"     "$SHAREPOINT_TENANT_ID"
store_secret "${SECRET_PREFIX}-hec-token"     "$SPLUNK_HEC_TOKEN"
store_secret "${SECRET_PREFIX}-hec-url"       "$HEC_URL"
store_secret "${SECRET_PREFIX}-index-name"    "$SPLUNK_INDEX"

# ---------------------------------------------------------------------------
# 4. Create S3 data bucket (idempotent)
# ---------------------------------------------------------------------------
echo -e "\n[4/9] Setting up S3 data bucket..."
if aws s3api head-bucket --bucket "$S3_DATA_BUCKET" 2>/dev/null; then
  echo "  S3 bucket already exists: $S3_DATA_BUCKET"
else
  # us-east-1 does not accept LocationConstraint
  if [[ "$AWS_REGION" == "us-east-1" ]]; then
    aws s3api create-bucket --bucket "$S3_DATA_BUCKET" --region "$AWS_REGION" --output json > /dev/null
  else
    aws s3api create-bucket \
      --bucket "$S3_DATA_BUCKET" \
      --region "$AWS_REGION" \
      --create-bucket-configuration "LocationConstraint=${AWS_REGION}" \
      --output json > /dev/null
  fi
  # Block all public access
  aws s3api put-public-access-block \
    --bucket "$S3_DATA_BUCKET" \
    --public-access-block-configuration \
      "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" \
    --output json > /dev/null
  echo "  S3 bucket created: $S3_DATA_BUCKET"
fi

# ---------------------------------------------------------------------------
# 5. Create DynamoDB tables (idempotent)
# ---------------------------------------------------------------------------
echo -e "\n[5/9] Setting up DynamoDB tables..."

# Changes table (all status transitions)
if aws dynamodb describe-table --table-name "$DYNAMODB_TABLE" &>/dev/null; then
  echo "  Table already exists: $DYNAMODB_TABLE"
else
  aws dynamodb create-table \
    --table-name "$DYNAMODB_TABLE" \
    --attribute-definitions \
      "AttributeName=item_key,AttributeType=S" \
      "AttributeName=detected_date,AttributeType=S" \
    --key-schema \
      "AttributeName=item_key,KeyType=HASH" \
      "AttributeName=detected_date,KeyType=RANGE" \
    --global-secondary-indexes '[{
      "IndexName": "date-index",
      "KeySchema": [
        {"AttributeName": "detected_date", "KeyType": "HASH"},
        {"AttributeName": "item_key",      "KeyType": "RANGE"}
      ],
      "Projection": {"ProjectionType": "ALL"}
    }]' \
    --billing-mode PAY_PER_REQUEST \
    --output json > /dev/null

  aws dynamodb wait table-exists --table-name "$DYNAMODB_TABLE"
  echo "  Created: $DYNAMODB_TABLE  (PK=item_key, SK=detected_date, GSI=date-index)"
fi

# Achievements table (on_roadmap -> compliant transitions only)
if aws dynamodb describe-table --table-name "$ACHIEVEMENTS_TABLE" &>/dev/null; then
  echo "  Table already exists: $ACHIEVEMENTS_TABLE"
else
  aws dynamodb create-table \
    --table-name "$ACHIEVEMENTS_TABLE" \
    --attribute-definitions \
      "AttributeName=achievement_key,AttributeType=S" \
      "AttributeName=achieved_date,AttributeType=S" \
    --key-schema \
      "AttributeName=achievement_key,KeyType=HASH" \
      "AttributeName=achieved_date,KeyType=RANGE" \
    --global-secondary-indexes '[{
      "IndexName": "date-index",
      "KeySchema": [
        {"AttributeName": "achieved_date",   "KeyType": "HASH"},
        {"AttributeName": "achievement_key", "KeyType": "RANGE"}
      ],
      "Projection": {"ProjectionType": "ALL"}
    }]' \
    --billing-mode PAY_PER_REQUEST \
    --output json > /dev/null

  aws dynamodb wait table-exists --table-name "$ACHIEVEMENTS_TABLE"
  echo "  Created: $ACHIEVEMENTS_TABLE  (PK=achievement_key, SK=achieved_date, GSI=date-index)"
  echo "    Fields: product, feature, infrastructure, certification, original_expected_date"
fi

# ---------------------------------------------------------------------------
# 6. Build Lambda deployment package
# ---------------------------------------------------------------------------
echo -e "\n[6/9] Building Lambda package..."
BUILD_DIR="$SCRIPT_DIR/build"
rm -rf "$BUILD_DIR" && mkdir -p "$BUILD_DIR"

pip3 install -r "$SCRIPT_DIR/requirements.txt" -t "$BUILD_DIR" -q \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.11 \
  --only-binary=:all: \
  --upgrade

cp "$SCRIPT_DIR/lambda_function.py" "$BUILD_DIR/"

cd "$BUILD_DIR"
zip -r9q "$SCRIPT_DIR/lambda_package.zip" .
cd "$SCRIPT_DIR"
echo "  Package built: $(du -sh lambda_package.zip | cut -f1)"

# ---------------------------------------------------------------------------
# 7. Deploy Lambda (via S3 for large packages)
# ---------------------------------------------------------------------------
echo -e "\n[7/9] Deploying Lambda function..."

S3_LAMBDA_BUCKET="sharepoint-compliance-lambda-${AWS_ACCOUNT}"
S3_KEY="lambda_package.zip"

if ! aws s3api head-bucket --bucket "$S3_LAMBDA_BUCKET" 2>/dev/null; then
  if [[ "$AWS_REGION" == "us-east-1" ]]; then
    aws s3api create-bucket --bucket "$S3_LAMBDA_BUCKET" --region "$AWS_REGION" --output json > /dev/null 2>&1 || true
  else
    aws s3api create-bucket \
      --bucket "$S3_LAMBDA_BUCKET" \
      --region "$AWS_REGION" \
      --create-bucket-configuration "LocationConstraint=${AWS_REGION}" \
      --output json > /dev/null
  fi
  echo "  S3 Lambda bucket created: $S3_LAMBDA_BUCKET"
fi

aws s3 cp "$SCRIPT_DIR/lambda_package.zip" "s3://${S3_LAMBDA_BUCKET}/${S3_KEY}" --quiet
echo "  Package uploaded to s3://${S3_LAMBDA_BUCKET}/${S3_KEY}"

# Wait for role to be assumable (new roles need ~10s)
sleep 10

LAMBDA_ENV="Variables={SECRET_PREFIX=${SECRET_PREFIX},AWS_REGION_NAME=${AWS_REGION},S3_DATA_BUCKET=${S3_DATA_BUCKET},DYNAMODB_CHANGES_TABLE=${DYNAMODB_TABLE},ACHIEVEMENTS_TABLE=${ACHIEVEMENTS_TABLE}}"

FUNCTION_ARN="arn:aws:lambda:${AWS_REGION}:${AWS_ACCOUNT}:function:${FUNCTION_NAME}"

if aws lambda get-function --function-name "$FUNCTION_NAME" &>/dev/null; then
  aws lambda update-function-code \
    --function-name "$FUNCTION_NAME" \
    --s3-bucket "$S3_LAMBDA_BUCKET" \
    --s3-key "$S3_KEY" \
    --output json > /dev/null
  echo "  Lambda code updated"

  aws lambda wait function-updated --function-name "$FUNCTION_NAME"

  aws lambda update-function-configuration \
    --function-name "$FUNCTION_NAME" \
    --timeout 300 \
    --memory-size 512 \
    --environment "$LAMBDA_ENV" \
    --output json > /dev/null
  echo "  Lambda configuration updated"
else
  aws lambda create-function \
    --function-name "$FUNCTION_NAME" \
    --runtime python3.11 \
    --role "$ROLE_ARN" \
    --handler lambda_function.lambda_handler \
    --s3-bucket "$S3_LAMBDA_BUCKET" \
    --s3-key "$S3_KEY" \
    --timeout 300 \
    --memory-size 512 \
    --environment "$LAMBDA_ENV" \
    --description "Syncs SharePoint compliance data to Splunk HEC + S3 daily snapshots" \
    --output json > /dev/null
  echo "  Lambda function created"
fi

# ---------------------------------------------------------------------------
# 8. Set up daily EventBridge schedule (replace hourly if present)
# ---------------------------------------------------------------------------
echo -e "\n[8/9] Setting up daily EventBridge schedule..."

# Remove old hourly rule if it exists
if aws events describe-rule --name "$OLD_RULE_NAME" &>/dev/null; then
  aws events remove-targets --rule "$OLD_RULE_NAME" --ids "1" --output json > /dev/null 2>&1 || true
  aws events delete-rule --name "$OLD_RULE_NAME" --output json > /dev/null
  echo "  Removed old hourly rule: $OLD_RULE_NAME"
fi

if aws events describe-rule --name "$RULE_NAME" &>/dev/null; then
  echo "  Daily schedule rule already exists: $RULE_NAME"
else
  aws events put-rule \
    --name "$RULE_NAME" \
    --schedule-expression "$SCHEDULE_EXPRESSION" \
    --state ENABLED \
    --description "Daily trigger (6 AM UTC) for SharePoint compliance sync" \
    --output json > /dev/null

  aws lambda add-permission \
    --function-name "$FUNCTION_NAME" \
    --statement-id "allow-eventbridge-${RULE_NAME}" \
    --action "lambda:InvokeFunction" \
    --principal "events.amazonaws.com" \
    --source-arn "arn:aws:events:${AWS_REGION}:${AWS_ACCOUNT}:rule/${RULE_NAME}" \
    --output json > /dev/null

  aws events put-targets \
    --rule "$RULE_NAME" \
    --targets "Id=1,Arn=${FUNCTION_ARN}" \
    --output json > /dev/null

  echo "  Daily schedule created: $SCHEDULE_EXPRESSION"
fi

# ---------------------------------------------------------------------------
# 9. Smoke test
# ---------------------------------------------------------------------------
echo -e "\n[9/9] Running smoke test (synchronous invoke)..."
RESULT_FILE="$SCRIPT_DIR/invoke_result.json"

aws lambda invoke \
  --function-name "$FUNCTION_NAME" \
  --invocation-type RequestResponse \
  --log-type Tail \
  --payload '{}' \
  --cli-binary-format raw-in-base64-out \
  "$RESULT_FILE" \
  --output json > /tmp/invoke_meta.json

STATUS_CODE=$(python3 -c "import json; print(json.load(open('$RESULT_FILE')).get('statusCode', 'unknown'))" 2>/dev/null || echo "unknown")
echo "  HTTP status: $STATUS_CODE"

if [[ "$STATUS_CODE" == "200" ]]; then
  echo "  Smoke test passed"
  python3 -c "
import json
result = json.load(open('$RESULT_FILE'))
body = json.loads(result['body'])
sp = body.get('sharepoint', {})
sl = body.get('splunk', {})
s3 = body.get('s3', {})
print(f\"  Rows from SharePoint  : {sp.get('rows_extracted')}\")
print(f\"  Events sent to Splunk : {sl.get('events_sent')} / {sl.get('events_created')}\")
print(f\"  S3 key                : {s3.get('key')}\")
print(f\"  Status changes found  : {s3.get('changes_detected')}\")
print(f\"  Roadmap -> Compliant  : {s3.get('roadmap_completions')}\")
print(f\"  Duration              : {body.get('duration_seconds')}s\")
"
else
  echo "  Smoke test FAILED - check invoke_result.json"
  cat "$RESULT_FILE"
fi

echo ""
echo "================================================================"
echo "Deployment complete!"
echo "  Function ARN      : $FUNCTION_ARN"
echo "  Schedule          : $SCHEDULE_EXPRESSION (6 AM UTC daily)"
echo ""
echo "  S3 daily snapshots: s3://${S3_DATA_BUCKET}/compliance-runs/year=YYYY/month=MM/day=DD/compliance.csv"
echo "  S3 latest baseline: s3://${S3_DATA_BUCKET}/latest/compliance_latest.csv"
echo "  S3 achievements   : s3://${S3_DATA_BUCKET}/achievement-history/year=YYYY/month=MM/day=DD/achievements.csv"
echo ""
echo "  DynamoDB changes  : ${DYNAMODB_TABLE}     (PK=item_key, SK=detected_date)"
echo "  DynamoDB achieved : ${ACHIEVEMENTS_TABLE} (PK=achievement_key, SK=achieved_date)"
echo "    Fields: product, feature, infrastructure, certification, original_expected_date"
echo ""
echo "  Logs          : aws logs tail /aws/lambda/$FUNCTION_NAME --follow --profile $AWS_PROFILE"
echo "  Manual invoke : aws lambda invoke --function-name $FUNCTION_NAME --payload '{}' --cli-binary-format raw-in-base64-out out.json --profile $AWS_PROFILE"
echo ""
echo "  Query achievements by date:"
echo "    aws dynamodb query --table-name $ACHIEVEMENTS_TABLE \\"
echo "      --index-name date-index \\"
echo "      --key-condition-expression 'achieved_date = :d' \\"
echo "      --expression-attribute-values '{\":d\":{\"S\":\"2026-06-26\"}}' \\"
echo "      --profile $AWS_PROFILE"
echo "================================================================"
