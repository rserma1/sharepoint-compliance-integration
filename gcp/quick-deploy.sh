#!/bin/bash

# Quick Deployment Script for pmops-docai-dev-e93d
# Usage: ./quick-deploy.sh

set -e

# Project Configuration
PROJECT_ID="pmops-docai-dev-e93d"
PROJECT_NUMBER="919201129170"
REGION="us-central1"
FUNCTION_NAME="sharepoint-compliance-processor"
BUCKET_NAME="product-compliance-data-pmops-docai-dev-e93d"

echo "=========================================="
echo "Quick Deploy to GCP - SharePoint Compliance"
echo "=========================================="
echo "Project ID: $PROJECT_ID"
echo "Region: $REGION"
echo "Function: $FUNCTION_NAME"
echo "Bucket: $BUCKET_NAME"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ Error: gcloud CLI not installed"
    echo "Install from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Authenticate and set project
echo "🔐 Authenticating to GCP..."
gcloud auth login
gcloud config set project $PROJECT_ID

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
SA_EMAIL="${FUNCTION_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
echo "🔐 Creating service account: $SA_EMAIL"

if ! gcloud iam service-accounts describe "$SA_EMAIL" &>/dev/null; then
    gcloud iam service-accounts create "$FUNCTION_NAME" \
        --display-name="SharePoint Compliance Processor" \
        --description="Service account for SharePoint compliance data processing"
    echo "✅ Service account created"
else
    echo "✅ Service account already exists"
fi

# Grant permissions
echo "🔑 Granting permissions..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/storage.objectAdmin"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/logging.logWriter"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/monitoring.metricWriter"

# Create secrets
echo "🔐 Setting up secrets..."
SECRET_PREFIX="sharepoint-compliance"

echo "Please provide your SharePoint credentials:"
echo "1. SharePoint Client Secret:"
read -s CLIENT_SECRET
echo ""

echo "2. SharePoint Tenant ID:"
read -s TENANT_ID
echo ""

# Create secrets
echo "$CLIENT_SECRET" | gcloud secrets create "${SECRET_PREFIX}-client-secret" --data-file=- 2>/dev/null || echo "Secret already exists"
echo "$TENANT_ID" | gcloud secrets create "${SECRET_PREFIX}-tenant-id" --data-file=- 2>/dev/null || echo "Secret already exists"

# Optional Splunk setup
echo ""
echo "Configure Splunk HEC? (y/n)"
read -r CONFIGURE_SPLUNK

if [ "$CONFIGURE_SPLUNK" = "y" ]; then
    echo "3. Splunk Host (e.g., your-stack.splunkcloud.com):"
    read -r SPLUNK_HOST
    
    echo "4. Splunk HEC Token:"
    read -s SPLUNK_TOKEN
    echo ""
    
    echo "$SPLUNK_HOST" | gcloud secrets create "${SECRET_PREFIX}-splunk-host" --data-file=- 2>/dev/null || echo "Secret already exists"
    echo "$SPLUNK_TOKEN" | gcloud secrets create "${SECRET_PREFIX}-splunk-token" --data-file=- 2>/dev/null || echo "Secret already exists"
fi

# Create storage bucket
echo "📦 Creating Cloud Storage bucket..."
if ! gsutil ls "gs://$BUCKET_NAME" &>/dev/null; then
    gsutil mb -l "$REGION" "gs://$BUCKET_NAME"
    echo "✅ Created bucket: gs://$BUCKET_NAME"
else
    echo "✅ Bucket already exists: gs://$BUCKET_NAME"
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
    --service-account "$SA_EMAIL" \
    --timeout 540s \
    --memory 1024MiB \
    --set-env-vars="GCP_PROJECT=$PROJECT_ID,GCS_BUCKET=$BUCKET_NAME,SECRET_PREFIX=$SECRET_PREFIX"

# Get function URL
FUNCTION_URL=$(gcloud functions describe "$FUNCTION_NAME" --region "$REGION" --format='value(httpsUrl)')
echo "✅ Function deployed: $FUNCTION_URL"

# Create Cloud Scheduler job
echo "⏰ Creating Cloud Scheduler job..."
SCHEDULER_JOB="${FUNCTION_NAME}-scheduler"

# Delete existing job if it exists
gcloud scheduler jobs delete "$SCHEDULER_JOB" --region "$REGION" &>/dev/null || true

gcloud scheduler jobs create http "$SCHEDULER_JOB" \
    --schedule "0 6 * * *" \
    --http-method POST \
    --uri "$FUNCTION_URL" \
    --oidc-service-account-email "$SA_EMAIL" \
    --time-zone UTC \
    --description="Daily SharePoint compliance data processing"

echo "✅ Scheduler job created: $SCHEDULER_JOB"

# Test the function
echo "🧪 Testing the function..."
sleep 10

RESPONSE=$(curl -s -X POST "$FUNCTION_URL" -H "Content-Type: application/json" -d '{}')

if echo "$RESPONSE" | grep -q '"status":"success"'; then
    echo "✅ Function test passed"
else
    echo "⚠️ Function test may have failed. Response: $RESPONSE"
fi

echo ""
echo "=========================================="
echo "✅ Deployment Complete!"
echo "=========================================="
echo ""
echo "📊 Resources Created:"
echo "  • Cloud Function: $FUNCTION_NAME"
echo "  • Cloud Storage: gs://$BUCKET_NAME"
echo "  • Cloud Scheduler: $SCHEDULER_JOB"
echo "  • Service Account: $SA_EMAIL"
echo "  • Secrets: ${SECRET_PREFIX}-*"
echo ""
echo "🔗 Function URL: $FUNCTION_URL"
echo "⏰ Schedule: Daily at 6 AM UTC"
echo ""
echo "📊 Monitoring Links:"
echo "  • Console: https://console.cloud.google.com/home/dashboard?project=$PROJECT_ID"
echo "  • Functions: https://console.cloud.google.com/functions/list?project=$PROJECT_ID"
echo "  • Storage: https://console.cloud.google.com/storage/browser/$BUCKET_NAME"
echo "  • Logs: https://console.cloud.google.com/logs/viewer?project=$PROJECT_ID"
echo ""
echo "🔧 Management Commands:"
echo "  • View logs: gcloud functions logs read $FUNCTION_NAME --region $REGION"
echo "  • Test manually: curl -X POST $FUNCTION_URL"
echo "  • Update schedule: gcloud scheduler jobs update $SCHEDULER_JOB --schedule '0 8 * * *'"
echo "  • Check bucket: gsutil ls gs://$BUCKET_NAME"
echo ""
echo "📝 Next Steps:"
echo "  1. Monitor the first run in Cloud Logging"
echo "  2. Check CSV files in Cloud Storage"
echo "  3. Verify Splunk data (if configured)"
echo "  4. Set up alerts for failures"
echo ""
