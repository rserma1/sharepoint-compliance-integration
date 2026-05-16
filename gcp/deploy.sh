#!/bin/bash

# GCP Deployment Script for SharePoint Compliance Integration

set -e

# Configuration
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project)}"
REGION="${REGION:-us-central1}"
FUNCTION_NAME="${FUNCTION_NAME:-sharepoint-compliance-processor}"
BUCKET_NAME="${BUCKET_NAME:-product-compliance-data-${PROJECT_ID}}"
SCHEDULE="${SCHEDULE:-0 6 * * *}"  # Daily at 6 AM UTC

echo "=========================================="
echo "GCP SharePoint Compliance Deployment"
echo "=========================================="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Function: $FUNCTION_NAME"
echo "Bucket: $BUCKET_NAME"
echo "Schedule: $SCHEDULE"
echo ""

# Check if project is set
if [ -z "$PROJECT_ID" ]; then
    echo "❌ Error: PROJECT_ID not set"
    echo "Set with: export PROJECT_ID=your-project-id"
    exit 1
fi

echo "🔧 Setting up project..."
gcloud config set project "$PROJECT_ID"

# Enable required APIs
echo "📋 Enabling required APIs..."
gcloud services enable \
    cloudfunctions.googleapis.com \
    cloudscheduler.googleapis.com \
    secretmanager.googleapis.com \
    storage.googleapis.com \
    logging.googleapis.com \
    monitoring.googleapis.com \
    cloudbuild.googleapis.com

# Create service account
SERVICE_ACCOUNT="${FUNCTION_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
echo "🔐 Creating service account: $SERVICE_ACCOUNT"

if ! gcloud iam service-accounts describe "$SERVICE_ACCOUNT" &>/dev/null; then
    gcloud iam service-accounts create "$FUNCTION_NAME" \
        --display-name="SharePoint Compliance Processor" \
        --description="Service account for SharePoint compliance data processing"
fi

# Grant necessary permissions
echo "🔑 Granting permissions to service account..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/storage.objectAdmin"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/logging.logWriter"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/monitoring.metricWriter"

# Create GCS bucket
echo "📦 Creating Cloud Storage bucket..."
if ! gsutil ls "gs://$BUCKET_NAME" &>/dev/null; then
    gsutil mb -l "$REGION" "gs://$BUCKET_NAME"
    echo "✅ Created bucket: gs://$BUCKET_NAME"
else
    echo "✅ Bucket already exists: gs://$BUCKET_NAME"
fi

# Set up secrets
echo "🔐 Setting up secrets..."
SECRET_PREFIX="sharepoint-compliance"

# SharePoint secrets
echo "Please provide the following credentials:"
echo "1. SharePoint Client Secret:"
read -s CLIENT_SECRET
echo ""

echo "2. SharePoint Tenant ID:"
read -s TENANT_ID
echo ""

# Create secrets
echo "$CLIENT_SECRET" | gcloud secrets create "${SECRET_PREFIX}-client-secret" --data-file=-
echo "$TENANT_ID" | gcloud secrets create "${SECRET_PREFIX}-tenant-id" --data-file=-

# Optional Splunk secrets
echo ""
echo "Optional: Configure Splunk HEC? (y/n)"
read -r CONFIGURE_SPLUNK

if [ "$CONFIGURE_SPLUNK" = "y" ]; then
    echo "3. Splunk Host (e.g., your-stack.splunkcloud.com):"
    read -r SPLUNK_HOST
    
    echo "4. Splunk HEC Token:"
    read -s SPLUNK_TOKEN
    echo ""
    
    echo "$SPLUNK_HOST" | gcloud secrets create "${SECRET_PREFIX}-splunk-host" --data-file=-
    echo "$SPLUNK_TOKEN" | gcloud secrets create "${SECRET_PREFIX}-splunk-token" --data-file=-
fi

# Deploy Cloud Function
echo "🚀 Deploying Cloud Function..."
cd "$(dirname "$0")"

gcloud functions deploy "$FUNCTION_NAME" \
    --runtime python39 \
    --region "$REGION" \
    --trigger-http \
    --entry-point process_sharepoint_compliance \
    --source . \
    --service-account "$SERVICE_ACCOUNT" \
    --timeout 540s \
    --memory 1024MiB \
    --set-env-vars="GCP_PROJECT=$PROJECT_ID,GCS_BUCKET=$BUCKET_NAME,SECRET_PREFIX=$SECRET_PREFIX"

# Get function URL
FUNCTION_URL=$(gcloud functions describe "$FUNCTION_NAME" --region "$REGION" --format='value(httpsUrl)')
echo "✅ Function deployed: $FUNCTION_URL"

# Test the function
echo "🧪 Testing the function..."
curl -X POST "$FUNCTION_URL" -H "Content-Type: application/json" -d '{}'

# Create Cloud Scheduler job
echo "⏰ Creating Cloud Scheduler job..."
SCHEDULER_JOB="${FUNCTION_NAME}-scheduler"

# Delete existing job if it exists
gcloud scheduler jobs delete "$SCHEDULER_JOB" --region "$REGION" &>/dev/null || true

gcloud scheduler jobs create http "$SCHEDULER_JOB" \
    --schedule "$SCHEDULE" \
    --http-method POST \
    --uri "$FUNCTION_URL" \
    --oidc-service-account-email "$SERVICE_ACCOUNT" \
    --time-zone UTC \
    --description="Daily SharePoint compliance data processing"

echo "✅ Scheduler job created: $SCHEDULER_JOB"

# Enable the scheduler job
gcloud scheduler jobs run "$SCHEDULER_JOB" --region "$REGION"

echo ""
echo "=========================================="
echo "✅ Deployment Complete!"
echo "=========================================="
echo ""
echo "📊 Resources Created:"
echo "  • Cloud Function: $FUNCTION_NAME"
echo "  • Cloud Storage: gs://$BUCKET_NAME"
echo "  • Cloud Scheduler: $SCHEDULER_JOB"
echo "  • Service Account: $SERVICE_ACCOUNT"
echo "  • Secrets: ${SECRET_PREFIX}-*"
echo ""
echo "🔗 Function URL: $FUNCTION_URL"
echo "⏰ Schedule: $SCHEDULE (Daily at 6 AM UTC)"
echo ""
echo "📝 Next Steps:"
echo "  1. Monitor the first run in Cloud Logging"
echo "  2. Check CSV files in Cloud Storage"
echo "  3. Verify Splunk data (if configured)"
echo "  4. Set up alerts for failures"
echo ""
echo "🔧 Management Commands:"
echo "  • View logs: gcloud functions logs read $FUNCTION_NAME --region $REGION"
echo "  • Test manually: curl -X POST $FUNCTION_URL"
echo "  • Update schedule: gcloud scheduler jobs update $SCHEDULER_JOB --schedule '0 8 * * *'"
echo ""
