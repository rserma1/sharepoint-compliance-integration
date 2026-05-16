# GCP Deployment Guide - pmops-docai-dev-e93d

## Project Information
- **Project ID**: `pmops-docai-dev-e93d`
- **Project Number**: `919201129170`
- **Region**: `us-central1` (recommended)

## Quick Start

### Option 1: Direct Deployment (Recommended for testing)

```bash
# 1. Set up GCP CLI
gcloud auth login
gcloud config set project pmops-docai-dev-e93d

# 2. Navigate to GCP directory
cd sharepoint-integration/gcp

# 3. Run deployment script
chmod +x deploy.sh
./deploy.sh
```

### Option 2: GitHub/GitLab CI/CD (Recommended for production)

#### GitHub Actions Setup
1. Fork/Clone repository to GitHub
2. Set up GitHub Secrets:
   - `GCP_PROJECT_ID`: `pmops-docai-dev-e93d`
   - `GCP_SA_KEY`: Service account JSON key
   - `SHAREPOINT_CLIENT_SECRET`
   - `SHAREPOINT_TENANT_ID`
   - `SPLUNK_HOST` (optional)
   - `SPLUNK_HEC_TOKEN` (optional)

#### GitLab CI/CD Setup
1. Set up GitLab CI/CD variables:
   - `GCP_PROJECT_ID`: `pmops-docai-dev-e93d`
   - `GCP_SA_KEY`: Service account JSON key
   - Same SharePoint/Splunk credentials as above

### Option 3: Container Deployment

```bash
# 1. Build and push to Artifact Registry
gcloud auth configure-docker us-central1-docker.pkg.dev
docker build -t us-central1-docker.pkg.dev/pmops-docai-dev-e93d/sharepoint-compliance/processor:latest .

# 2. Push to registry
docker push us-central1-docker.pkg.dev/pmops-docai-dev-e93d/sharepoint-compliance/processor:latest

# 3. Deploy to Cloud Run
gcloud run deploy sharepoint-compliance-processor \
    --image us-central1-docker.pkg.dev/pmops-docai-dev-e93d/sharepoint-compliance/processor:latest \
    --platform managed \
    --region us-central1 \
    --allow-unauthenticated \
    --memory 1Gi \
    --timeout 15m
```

## Detailed Deployment Steps

### Step 1: Project Setup

```bash
# Set your project
gcloud config set project pmops-docai-dev-e93d

# Enable required APIs
gcloud services enable \
    cloudfunctions.googleapis.com \
    cloudscheduler.googleapis.com \
    secretmanager.googleapis.com \
    storage.googleapis.com \
    logging.googleapis.com \
    monitoring.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    run.googleapis.com

# Set default region
gcloud config set compute/region us-central1
gcloud config set functions/region us-central1
```

### Step 2: Service Account Setup

```bash
# Create service account
gcloud iam service-accounts create sharepoint-compliance-processor \
    --display-name="SharePoint Compliance Processor" \
    --description="Service account for SharePoint compliance data processing"

# Grant permissions
PROJECT_ID="pmops-docai-dev-e93d"
SA_EMAIL="sharepoint-compliance-processor@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/storage.objectAdmin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/logging.logWriter"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/monitoring.metricWriter"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/cloudscheduler.admin"

# Create service account key for CI/CD
gcloud iam service-accounts keys create ~/sharepoint-sa-key.json \
    --iam-account $SA_EMAIL
```

### Step 3: Secret Manager Setup

```bash
# Create secrets (replace with actual values)
echo "YOUR_SHAREPOINT_CLIENT_SECRET" | gcloud secrets create sharepoint-compliance-client-secret --data-file=-
echo "YOUR_SHAREPOINT_TENANT_ID" | gcloud secrets create sharepoint-compliance-tenant-id --data-file=-

# Optional Splunk secrets
echo "your-stack.splunkcloud.com" | gcloud secrets create sharepoint-compliance-splunk-host --data-file=-
echo "YOUR_SPLUNK_HEC_TOKEN" | gcloud secrets create sharepoint-compliance-splunk-token --data-file=-

# Verify secrets
gcloud secrets list --filter="name~sharepoint-compliance"
```

### Step 4: Cloud Storage Setup

```bash
# Create bucket
BUCKET_NAME="product-compliance-data-pmops-docai-dev-e93d"
gsutil mb -l us-central1 gs://$BUCKET_NAME

# Set lifecycle rules (optional)
cat > lifecycle.json << EOF
{
  "rule": [
    {
      "action": {"type": "Delete"},
      "condition": {"age": 30}
    }
  ]
}
EOF

gsutil lifecycle set lifecycle.json gs://$BUCKET_NAME
```

### Step 5: Deploy Cloud Function

```bash
cd sharepoint-integration/gcp

# Deploy function
gcloud functions deploy sharepoint-compliance-processor \
    --runtime python39 \
    --region us-central1 \
    --trigger-http \
    --entry-point process_sharepoint_compliance \
    --source . \
    --service-account $SA_EMAIL \
    --timeout 540s \
    --memory 1024MiB \
    --set-env-vars="GCP_PROJECT=pmops-docai-dev-e93d,GCS_BUCKET=$BUCKET_NAME,SECRET_PREFIX=sharepoint-compliance"

# Get function URL
FUNCTION_URL=$(gcloud functions describe sharepoint-compliance-processor --region us-central1 --format='value(httpsUrl)')
echo "Function URL: $FUNCTION_URL"
```

### Step 6: Cloud Scheduler Setup

```bash
# Create scheduler job
gcloud scheduler jobs create http sharepoint-compliance-scheduler \
    --schedule "0 6 * * *" \
    --http-method POST \
    --uri $FUNCTION_URL \
    --oidc-service-account-email $SA_EMAIL \
    --time-zone UTC \
    --description="Daily SharePoint compliance data processing"

# Test the scheduler
gcloud scheduler jobs run sharepoint-compliance-scheduler --location us-central1
```

## CI/CD Setup

### GitHub Actions

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy SharePoint Compliance Processor

on:
  push:
    branches: [ main ]
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    
    - name: Setup GCP
      uses: google-github-actions/setup-gcloud@v0
      with:
        project_id: pmops-docai-dev-e93d
        service_account_key: ${{ secrets.GCP_SA_KEY }}
    
    - name: Deploy to Cloud Functions
      run: |
        cd sharepoint-integration/gcp
        gcloud functions deploy sharepoint-compliance-processor \
          --runtime python39 \
          --region us-central1 \
          --trigger-http \
          --entry-point process_sharepoint_compliance \
          --source . \
          --timeout 540s \
          --memory 1024MiB \
          --set-env-vars="GCP_PROJECT=pmops-docai-dev-e93d,GCS_BUCKET=product-compliance-data-pmops-docai-dev-e93d,SECRET_PREFIX=sharepoint-compliance"
```

### GitLab CI/CD

Create `.gitlab-ci.yml`:

```yaml
stages:
  - deploy

deploy_to_gcp:
  stage: deploy
  image: google/cloud-sdk:latest
  script:
    - echo $GCP_SA_KEY > ~/gcp-key.json
    - gcloud auth activate-service-account --key-file ~/gcp-key.json
    - gcloud config set project pmops-docai-dev-e93d
    - cd sharepoint-integration/gcp
    - gcloud functions deploy sharepoint-compliance-processor \
        --runtime python39 \
        --region us-central1 \
        --trigger-http \
        --entry-point process_sharepoint_compliance \
        --source . \
        --timeout 540s \
        --memory 1024MiB \
        --set-env-vars="GCP_PROJECT=pmops-docai-dev-e93d,GCS_BUCKET=product-compliance-data-pmops-docai-dev-e93d,SECRET_PREFIX=sharepoint-compliance"
  only:
    - main
```

## Container Deployment (Alternative)

### Build and Deploy Container

```bash
# 1. Enable Artifact Registry
gcloud services enable artifactregistry.googleapis.com

# 2. Create repository
gcloud artifacts repositories create sharepoint-compliance \
    --repository-format=docker \
    --location=us-central1 \
    --description="SharePoint compliance processor images"

# 3. Build and push
cd sharepoint-integration/gcp
gcloud builds submit --tag us-central1-docker.pkg.dev/pmops-docai-dev-e93d/sharepoint-compliance/processor:latest .

# 4. Deploy to Cloud Run
gcloud run deploy sharepoint-compliance-processor \
    --image us-central1-docker.pkg.dev/pmops-docai-dev-e93d/sharepoint-compliance/processor:latest \
    --platform managed \
    --region us-central1 \
    --allow-unauthenticated \
    --memory 1Gi \
    --timeout 15m \
    --set-env-vars="GCP_PROJECT=pmops-docai-dev-e93d,GCS_BUCKET=product-compliance-data-pmops-docai-dev-e93d,SECRET_PREFIX=sharepoint-compliance"

# 5. Create scheduler for Cloud Run
SERVICE_URL=$(gcloud run services describe sharepoint-compliance-processor --region us-central1 --format='value(status.url)')
gcloud scheduler jobs create http sharepoint-compliance-scheduler \
    --schedule "0 6 * * *" \
    --http-method POST \
    --uri $SERVICE_URL \
    --oidc-service-account-email $SA_EMAIL \
    --time-zone UTC
```

## Verification and Testing

### Test Deployment

```bash
# Test Cloud Function
FUNCTION_URL=$(gcloud functions describe sharepoint-compliance-processor --region us-central1 --format='value(httpsUrl)')
curl -X POST "$FUNCTION_URL" -H "Content-Type: application/json" -d '{}'

# Test Cloud Run (if deployed)
SERVICE_URL=$(gcloud run services describe sharepoint-compliance-processor --region us-central1 --format='value(status.url)')
curl -X POST "$SERVICE_URL" -H "Content-Type: application/json" -d '{}'

# Check logs
gcloud functions logs read sharepoint-compliance-processor --region us-central1 --limit 50

# Check Cloud Storage
gsutil ls gs://product-compliance-data-pmops-docai-dev-e93d
```

### Monitor Deployment

```bash
# Check function status
gcloud functions describe sharepoint-compliance-processor --region us-central1

# Check scheduler status
gcloud scheduler jobs describe sharepoint-compliance-scheduler --location us-central1

# View logs in Cloud Console
echo "https://console.cloud.google.com/logs/viewer?project=pmops-docai-dev-e93d"

# View monitoring dashboard
echo "https://console.cloud.google.com/monitoring/dashboards?project=pmops-docai-dev-e93d"
```

## Cost Management

### Estimated Monthly Costs
- **Cloud Functions**: $0.10 - $1.00 (daily runs)
- **Cloud Storage**: $0.02 - $0.05 (CSV storage)
- **Secret Manager**: $0.03 (per secret)
- **Cloud Logging**: $0.50 (log retention)
- **Cloud Scheduler**: $0.03 (monthly job)
- **Total**: ~$0.68 - $1.61 per month

### Cost Optimization
```bash
# Set log retention (30 days)
gcloud logging sinks update sharepoint-compliance-logs \
    --log-filter='resource.type="cloud_function"' \
    --retention-days=30

# Enable Cloud Storage lifecycle rules
gsutil lifecycle set lifecycle.json gs://product-compliance-data-pmops-docai-dev-e93d
```

## Troubleshooting

### Common Issues

#### Permission Denied
```bash
# Check service account permissions
gcloud projects get-iam-policy pmops-docai-dev-e93d --flatten="bindings[].members" --format="table(bindings.role, bindings.members)"

# Grant missing permissions
gcloud projects add-iam-policy-binding pmops-docai-dev-e93d \
    --member="serviceAccount:sharepoint-compliance-processor@pmops-docai-dev-e93d.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
```

#### Function Timeout
```bash
# Increase timeout
gcloud functions deploy sharepoint-compliance-processor \
    --timeout 540s \
    --memory 1024MiB
```

#### Secret Access Issues
```bash
# Test secret access
gcloud secrets versions access sharepoint-compliance-client-secret --latest

# Grant secret access
gcloud secrets add-iam-policy-binding sharepoint-compliance-client-secret \
    --member="serviceAccount:sharepoint-compliance-processor@pmops-docai-dev-e93d.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
```

## Next Steps

1. **Choose deployment method** (Direct, CI/CD, or Container)
2. **Set up credentials** in Secret Manager
3. **Deploy using chosen method**
4. **Test the deployment**
5. **Set up monitoring and alerts**
6. **Configure automated schedule**
7. **Document for team**

## Support Resources

- **GCP Console**: https://console.cloud.google.com/
- **Project Dashboard**: https://console.cloud.google.com/home/dashboard?project=pmops-docai-dev-e93d
- **Cloud Functions**: https://console.cloud.google.com/functions/list?project=pmops-docai-dev-e93d
- **Secret Manager**: https://console.cloud.google.com/security/secret-manager?project=pmops-docai-dev-e93d
- **Cloud Storage**: https://console.cloud.google.com/storage/browser?project=pmops-docai-dev-e93d
