#!/bin/bash

# Production Test Deployment Script for SharePoint Compliance Integration
# This script deploys a test function that connects to real SharePoint

set -e

PROJECT_ID="pmops-docai-dev-e93d"
REGION="us-central1"
FUNCTION_NAME="sharepoint-compliance-prod-test"
BUCKET_NAME="product-compliance-data-pmops-docai-dev-e93d"

echo "🚀 Deploying SharePoint Compliance Production Test Function"
echo "=================================================="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Function: $FUNCTION_NAME"
echo "=================================================="

# Set project
echo "📋 Setting GCP project..."
gcloud config set project $PROJECT_ID

# Check if client-id secret exists, if not create it
echo "🔐 Checking secrets..."
if ! gcloud secrets describe sharepoint-compliance-client-id &>/dev/null; then
    echo "Creating sharepoint-compliance-client-id secret..."
    echo "6f9ebeed-1c0c-4cdb-a7cb-19718966e3bc" | gcloud secrets create sharepoint-compliance-client-id --data-file=-
else
    echo "✅ sharepoint-compliance-client-id exists"
fi

# Verify all required secrets exist
echo "📋 Verifying required secrets..."
REQUIRED_SECRETS=(
    "sharepoint-compliance-client-id"
    "sharepoint-compliance-client-secret"
    "sharepoint-compliance-tenant-id"
)

for secret in "${REQUIRED_SECRETS[@]}"; do
    if gcloud secrets describe $secret &>/dev/null; then
        echo "✅ $secret exists"
    else
        echo "❌ ERROR: Secret $secret does not exist!"
        echo "Please create it with: gcloud secrets create $secret --data-file=-"
        exit 1
    fi
done

# Create service account if it doesn't exist
echo "👤 Creating service account..."
SA_EMAIL="${FUNCTION_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

if ! gcloud iam service-accounts describe $SA_EMAIL &>/dev/null; then
    gcloud iam service-accounts create $FUNCTION_NAME \
        --display-name="SharePoint Compliance Prod Test" \
        --description="Service account for SharePoint compliance data processing (prod test)"
else
    echo "✅ Service account exists"
fi

# Grant permissions
echo "🔑 Granting permissions..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/secretmanager.secretAccessor" \
    --condition=None 2>/dev/null || true

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/storage.objectAdmin" \
    --condition=None 2>/dev/null || true

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/logging.logWriter" \
    --condition=None 2>/dev/null || true

# Create bucket if it doesn't exist
echo "🪣 Creating storage bucket..."
if ! gsutil ls "gs://${BUCKET_NAME}" &>/dev/null; then
    gsutil mb -l $REGION "gs://${BUCKET_NAME}"
else
    echo "✅ Bucket exists"
fi

# Copy production test function to main.py
echo "📝 Preparing function code..."
cp main_prod_test.py main.py

# Deploy function
echo "🚀 Deploying Cloud Function..."
gcloud functions deploy $FUNCTION_NAME \
    --runtime=python311 \
    --region=$REGION \
    --source=. \
    --entry-point=process_sharepoint_compliance_test \
    --trigger-http \
    --allow-unauthenticated \
    --timeout=540s \
    --memory=1024MiB \
    --service-account="$SA_EMAIL" \
    --set-env-vars="GCP_PROJECT=$PROJECT_ID,GCS_BUCKET=$BUCKET_NAME,SECRET_PREFIX=sharepoint-compliance"

# Get function URL
echo ""
echo "🎉 Deployment Complete!"
echo "=================================================="
FUNCTION_URL=$(gcloud functions describe $FUNCTION_NAME --region=$REGION --format='value(httpsTrigger.url)')
echo "Function URL: $FUNCTION_URL"
echo ""
echo "🧪 Test the function:"
echo "curl -X POST $FUNCTION_URL"
echo ""
echo "📊 View logs:"
echo "gcloud functions logs read $FUNCTION_NAME --region=$REGION --limit=50"
echo ""
echo "☁️ Check Cloud Storage:"
echo "gsutil ls gs://$BUCKET_NAME"
echo "=================================================="
