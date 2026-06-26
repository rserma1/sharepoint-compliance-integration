#!/usr/bin/env bash
# Deploy SharePoint Regional Availability -> Splunk Lambda to splk-pmops-dev-1 (676878928498)
# Same pattern as deploy.sh (compliance), separate function + DynamoDB table.
# Shares: IAM role, Secrets Manager, S3 data bucket, EventBridge schedule.
set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
AWS_PROFILE="splk-pmops-dev-1_splkcld_account_admin"
AWS_REGION="us-east-1"
AWS_ACCOUNT="676878928498"

FUNCTION_NAME="sharepoint-rac-sync"
LAMBDA_ROLE_NAME="sharepoint-compliance-lambda-role"   # shared with compliance Lambda
SECRET_PREFIX="sharepoint-compliance"                  # shared secrets

# Daily at 6 AM UTC (same time as compliance; independent Lambda, no conflict)
SCHEDULE_EXPRESSION="cron(0 6 * * ? *)"
RULE_NAME="${FUNCTION_NAME}-daily"

# Shared S3 data bucket (RAC data goes to rac-runs/ prefix)
S3_DATA_BUCKET="sharepoint-compliance-data-${AWS_ACCOUNT}"

# DynamoDB table for RAC status-change tracking
DYNAMODB_TABLE="sharepoint-rac-changes"

# SharePoint sheet names — update these if the actual names differ
RAC_PRODUCT_SHEET="Regional Availability(Product)"
RAC_FEATURE_SHEET="Regional Availability(Feature)"

# SharePoint File ID — update if RAC data lives in a different workbook
# Defaults to the same compliance workbook; set RAC_FILE_ID env var to override
RAC_FILE_ID="${RAC_FILE_ID:-F07872BA-6EA5-40D0-A837-4A6505B4F336}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: .env not found at $ENV_FILE"
  exit 1
fi

set -a; source "$ENV_FILE"; set +a

: "${SHAREPOINT_CLIENT_ID:?SHAREPOINT_CLIENT_ID not set in .env}"
: "${SHAREPOINT_CLIENT_SECRET:?SHAREPOINT_CLIENT_SECRET not set in .env}"
: "${SHAREPOINT_TENANT_ID:?SHAREPOINT_TENANT_ID not set in .env}"
: "${SPLUNK_HEC_TOKEN:?SPLUNK_HEC_TOKEN not set in .env}"
: "${SPLUNK_INDEX:?SPLUNK_INDEX not set in .env}"

HEC_URL="https://http-inputs-products-telemetry.splunkcloud.com:443/services/collector/event"

export AWS_PROFILE AWS_REGION

echo "================================================================"
echo "Deploying SharePoint RAC -> Splunk Lambda"
echo "  Account        : $AWS_ACCOUNT"
echo "  Region         : $AWS_REGION"
echo "  Function       : $FUNCTION_NAME"
echo "  Schedule       : $SCHEDULE_EXPRESSION"
echo "  S3 data bucket : $S3_DATA_BUCKET  (prefix: rac-runs/)"
echo "  DynamoDB       : $DYNAMODB_TABLE"
echo "  Product sheet  : $RAC_PRODUCT_SHEET"
echo "  Feature sheet  : $RAC_FEATURE_SHEET"
echo "  File ID        : $RAC_FILE_ID"
echo "================================================================"

# ---------------------------------------------------------------------------
# 1. Verify AWS auth
# ---------------------------------------------------------------------------
echo -e "\n[1/8] Verifying AWS credentials..."
CALLER=$(aws sts get-caller-identity --output json)
echo "  Authenticated as: $(echo "$CALLER" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['Arn'])")"

# ---------------------------------------------------------------------------
# 2. IAM role already exists (shared with compliance Lambda)
# ---------------------------------------------------------------------------
echo -e "\n[2/8] Checking IAM role..."
if aws iam get-role --role-name "$LAMBDA_ROLE_NAME" &>/dev/null; then
  echo "  IAM role exists (shared): $LAMBDA_ROLE_NAME"
else
  echo "  ERROR: IAM role not found. Deploy the compliance Lambda first (deploy.sh)."
  exit 1
fi

# Extend inline policy to include the RAC DynamoDB table
DATA_POLICY=$(aws iam get-role-policy \
  --role-name "$LAMBDA_ROLE_NAME" \
  --policy-name "sharepoint-compliance-data-access" \
  --query 'PolicyDocument' --output json 2>/dev/null || echo "{}")

# Check if RAC table is already in the policy
if echo "$DATA_POLICY" | python3 -c "import sys,json; d=json.load(sys.stdin); stmts=d.get('Statement',[]); resources=[r for s in stmts for r in (s.get('Resource',[]) if isinstance(s.get('Resource'),list) else [s.get('Resource','')])] ; print('ok' if any('sharepoint-rac-changes' in r for r in resources) else 'missing')" | grep -q "^ok"; then
  echo "  RAC DynamoDB table already in IAM policy"
else
  echo "  Updating IAM inline policy to include RAC DynamoDB table..."
  UPDATED_POLICY="{
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
        \"arn:aws:dynamodb:${AWS_REGION}:${AWS_ACCOUNT}:table/sharepoint-compliance-changes\",
        \"arn:aws:dynamodb:${AWS_REGION}:${AWS_ACCOUNT}:table/sharepoint-compliance-changes/index/*\",
        \"arn:aws:dynamodb:${AWS_REGION}:${AWS_ACCOUNT}:table/sharepoint-compliance-achievements\",
        \"arn:aws:dynamodb:${AWS_REGION}:${AWS_ACCOUNT}:table/sharepoint-compliance-achievements/index/*\",
        \"arn:aws:dynamodb:${AWS_REGION}:${AWS_ACCOUNT}:table/${DYNAMODB_TABLE}\",
        \"arn:aws:dynamodb:${AWS_REGION}:${AWS_ACCOUNT}:table/${DYNAMODB_TABLE}/index/*\"
      ]
    }
  ]
}"
  aws iam put-role-policy \
    --role-name "$LAMBDA_ROLE_NAME" \
    --policy-name "sharepoint-compliance-data-access" \
    --policy-document "$UPDATED_POLICY" \
    --output json > /dev/null
  echo "  IAM policy updated"
fi

# ---------------------------------------------------------------------------
# 3. Create RAC DynamoDB table (idempotent)
# ---------------------------------------------------------------------------
echo -e "\n[3/8] Setting up DynamoDB table..."
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

# ---------------------------------------------------------------------------
# 4. Build Lambda deployment package
# ---------------------------------------------------------------------------
echo -e "\n[4/8] Building Lambda package..."
BUILD_DIR="$SCRIPT_DIR/build_rac"
rm -rf "$BUILD_DIR" && mkdir -p "$BUILD_DIR"

pip3 install -r "$SCRIPT_DIR/requirements.txt" -t "$BUILD_DIR" -q \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.11 \
  --only-binary=:all: \
  --upgrade

cp "$SCRIPT_DIR/lambda_rac.py" "$BUILD_DIR/lambda_function.py"

cd "$BUILD_DIR"
zip -r9q "$SCRIPT_DIR/lambda_rac_package.zip" .
cd "$SCRIPT_DIR"
echo "  Package built: $(du -sh lambda_rac_package.zip | cut -f1)"

# ---------------------------------------------------------------------------
# 5. Deploy Lambda via S3
# ---------------------------------------------------------------------------
echo -e "\n[5/8] Deploying Lambda function..."

S3_LAMBDA_BUCKET="sharepoint-compliance-lambda-${AWS_ACCOUNT}"
S3_KEY="lambda_rac_package.zip"

# Bucket already exists from compliance Lambda deploy
aws s3 cp "$SCRIPT_DIR/lambda_rac_package.zip" "s3://${S3_LAMBDA_BUCKET}/${S3_KEY}" --quiet
echo "  Package uploaded to s3://${S3_LAMBDA_BUCKET}/${S3_KEY}"

ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT}:role/${LAMBDA_ROLE_NAME}"
FUNCTION_ARN="arn:aws:lambda:${AWS_REGION}:${AWS_ACCOUNT}:function:${FUNCTION_NAME}"

# Write env as JSON file to avoid shell-escaping issues with parentheses in sheet names
LAMBDA_ENV_FILE=$(mktemp /tmp/lambda_rac_env_XXXXXX.json)
python3 - <<PYEOF > "$LAMBDA_ENV_FILE"
import json
print(json.dumps({"Variables": {
    "SECRET_PREFIX":             "${SECRET_PREFIX}",
    "AWS_REGION_NAME":           "${AWS_REGION}",
    "S3_DATA_BUCKET":            "${S3_DATA_BUCKET}",
    "RAC_DYNAMODB_CHANGES_TABLE": "${DYNAMODB_TABLE}",
    "RAC_FILE_ID":               "${RAC_FILE_ID}",
    "RAC_PRODUCT_SHEET":         "${RAC_PRODUCT_SHEET}",
    "RAC_FEATURE_SHEET":         "${RAC_FEATURE_SHEET}",
}}))
PYEOF

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
    --environment "file://$LAMBDA_ENV_FILE" \
    --output json > /dev/null
  echo "  Lambda configuration updated"
else
  sleep 5   # brief wait if role was just modified
  aws lambda create-function \
    --function-name "$FUNCTION_NAME" \
    --runtime python3.11 \
    --role "$ROLE_ARN" \
    --handler lambda_function.lambda_handler \
    --s3-bucket "$S3_LAMBDA_BUCKET" \
    --s3-key "$S3_KEY" \
    --timeout 300 \
    --memory-size 512 \
    --environment "file://$LAMBDA_ENV_FILE" \
    --description "Syncs SharePoint Regional Availability data to Splunk HEC + S3 daily snapshots" \
    --output json > /dev/null
  echo "  Lambda function created"
fi

# ---------------------------------------------------------------------------
# 6. EventBridge daily schedule
# ---------------------------------------------------------------------------
echo -e "\n[6/8] Setting up daily EventBridge schedule..."

if aws events describe-rule --name "$RULE_NAME" &>/dev/null; then
  echo "  Daily schedule rule already exists: $RULE_NAME"
else
  aws events put-rule \
    --name "$RULE_NAME" \
    --schedule-expression "$SCHEDULE_EXPRESSION" \
    --state ENABLED \
    --description "Daily trigger (6 AM UTC) for SharePoint RAC sync" \
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
# 7. Smoke test
# ---------------------------------------------------------------------------
echo -e "\n[7/8] Running smoke test (synchronous invoke)..."
RESULT_FILE="$SCRIPT_DIR/invoke_rac_result.json"

aws lambda invoke \
  --function-name "$FUNCTION_NAME" \
  --invocation-type RequestResponse \
  --log-type Tail \
  --payload '{}' \
  --cli-binary-format raw-in-base64-out \
  "$RESULT_FILE" \
  --output json > /tmp/invoke_rac_meta.json

STATUS_CODE=$(python3 -c "import json; print(json.load(open('$RESULT_FILE')).get('statusCode', 'unknown'))" 2>/dev/null || echo "unknown")
echo "  HTTP status: $STATUS_CODE"

if [[ "$STATUS_CODE" == "200" ]]; then
  echo "  Smoke test passed"
  python3 -c "
import json
result = json.load(open('$RESULT_FILE'))
body = json.loads(result['body'])
sp = body.get('sharepoint', {})
nm = body.get('normalization', {})
sl = body.get('splunk', {})
s3 = body.get('s3', {})
print(f\"  Product sheet rows  : {sp.get('product_raw_rows')}\")
print(f\"  Feature sheet rows  : {sp.get('feature_raw_rows')}\")
print(f\"  Product records     : {nm.get('product_records')}\")
print(f\"  Feature records     : {nm.get('feature_records')}\")
print(f\"  Total records       : {nm.get('total_records')}\")
print(f\"  Events sent to Splunk: {sl.get('events_sent')} / {sl.get('events_created')}\")
print(f\"  S3 key              : {s3.get('key')}\")
print(f\"  Status changes      : {s3.get('changes_detected')}\")
print(f\"  Duration            : {body.get('duration_seconds')}s\")
"
else
  echo "  Smoke test FAILED - check invoke_rac_result.json"
  cat "$RESULT_FILE"
fi

# ---------------------------------------------------------------------------
# 8. Summary
# ---------------------------------------------------------------------------
echo ""
echo "================================================================"
echo "Deployment complete!"
echo "  Function ARN  : $FUNCTION_ARN"
echo "  Schedule      : $SCHEDULE_EXPRESSION (6 AM UTC daily)"
echo ""
echo "  S3 daily      : s3://${S3_DATA_BUCKET}/rac-runs/year=YYYY/month=MM/day=DD/rac.csv"
echo "  S3 latest     : s3://${S3_DATA_BUCKET}/latest/rac_latest.csv"
echo "  DynamoDB      : ${DYNAMODB_TABLE} (PK=item_key, SK=detected_date)"
echo ""
echo "  Next step: create the Splunk saved search to refresh rdmp_reg_aval.csv"
echo "    See: splunk/savedsearches_rac.conf"
echo ""
echo "  NOTE: Confirm these sheet names match the actual SharePoint workbook:"
echo "    Product sheet : $RAC_PRODUCT_SHEET"
echo "    Feature sheet : $RAC_FEATURE_SHEET"
echo "  If they differ, set RAC_PRODUCT_SHEET / RAC_FEATURE_SHEET in .env"
echo "  and re-run this script."
echo ""
echo "  Logs          : aws logs tail /aws/lambda/$FUNCTION_NAME --follow --profile $AWS_PROFILE"
echo "  Manual invoke : aws lambda invoke --function-name $FUNCTION_NAME --payload '{}' --cli-binary-format raw-in-base64-out invoke_rac_result.json --profile $AWS_PROFILE --region $AWS_REGION"
echo "================================================================"
