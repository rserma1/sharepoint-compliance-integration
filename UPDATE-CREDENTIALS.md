# Update Credentials Guide - From Test to Production

## Overview

This guide explains how to update your deployed SharePoint integration from test mode (using seed data) to production mode (using real SharePoint credentials).

## What's Currently Deployed

Your test deployment includes:
- **Mock SharePoint credentials** (test values)
- **Seed data generation** (100 sample records)
- **Test Cloud Function**: `sharepoint-compliance-processor-test`
- **Seed Generator**: `sharepoint-seed-generator`
- **Daily scheduler** running at 6 AM UTC

## Step 1: Get Real Credentials

### SharePoint Credentials Required:
1. **Client Secret** - From Azure AD app `6f9ebeed-1c0c-4cdb-a7cb-19718966e3bc`
2. **Tenant ID** - Your Cisco Azure AD tenant ID

### Optional Splunk Credentials:
3. **Splunk Host** - e.g., `your-stack.splunkcloud.com`
4. **Splunk HEC Token** - From Splunk Cloud HTTP Event Collector

## Step 2: Update GCP Secrets

### Method 1: Using gcloud CLI

```bash
# Set your project
gcloud config set project pmops-docai-dev-e93d

# Update SharePoint secrets
echo "YOUR_REAL_CLIENT_SECRET" | gcloud secrets versions add sharepoint-compliance-client-secret --data-file=-
echo "YOUR_REAL_TENANT_ID" | gcloud secrets versions add sharepoint-compliance-tenant-id --data-file=-

# Update Splunk secrets (optional)
echo "your-stack.splunkcloud.com" | gcloud secrets versions add sharepoint-compliance-splunk-host --data-file=-
echo "YOUR_REAL_SPLUNK_HEC_TOKEN" | gcloud secrets versions add sharepoint-compliance-splunk-token --data-file=-
```

### Method 2: Using GCP Console

1. Go to: https://console.cloud.google.com/security/secret-manager?project=pmops-docai-dev-e93d
2. Find secrets starting with `sharepoint-compliance-`
3. Click each secret → "CREATE NEW VERSION"
4. Enter the real credential value
5. Click "CREATE"

## Step 3: Deploy Production Function

### Option 1: Update Existing Function

```bash
# Redeploy with production settings
cd sharepoint-integration/gcp

# Copy production function
cp main.py main_production.py

# Deploy production version
gcloud functions deploy sharepoint-compliance-processor \
    --runtime python39 \
    --region us-central1 \
    --trigger-http \
    --entry-point process_sharepoint_compliance \
    --source . \
    --service-account sharepoint-compliance-processor@pmops-docai-dev-e93d.iam.gserviceaccount.com \
    --timeout 540s \
    --memory 1024MiB \
    --set-env-vars="GCP_PROJECT=pmops-docai-dev-e93d,GCS_BUCKET=product-compliance-data-pmops-docai-dev-e93d,SECRET_PREFIX=sharepoint-compliance,USE_SEED_DATA=false"
```

### Option 2: Deploy New Production Function

```bash
# Deploy as new function
gcloud functions deploy sharepoint-compliance-processor-prod \
    --runtime python39 \
    --region us-central1 \
    --trigger-http \
    --entry-point process_sharepoint_compliance \
    --source . \
    --service-account sharepoint-compliance-processor@pmops-docai-dev-e93d.iam.gserviceaccount.com \
    --timeout 540s \
    --memory 1024MiB \
    --set-env-vars="GCP_PROJECT=pmops-docai-dev-e93d,GCS_BUCKET=product-compliance-data-pmops-docai-dev-e93d,SECRET_PREFIX=sharepoint-compliance,USE_SEED_DATA=false"
```

## Step 4: Update Scheduler

```bash
# Get production function URL
PROD_URL=$(gcloud functions describe sharepoint-compliance-processor --region us-central1 --format='value(httpsUrl)')

# Update scheduler to use production function
gcloud scheduler jobs update sharepoint-compliance-scheduler \
    --uri "$PROD_URL" \
    --location us-central1
```

## Step 5: Test Production Deployment

### Test the Function

```bash
# Get production function URL
PROD_URL=$(gcloud functions describe sharepoint-compliance-processor --region us-central1 --format='value(httpsUrl)')

# Test with curl
curl -X POST "$PROD_URL" -H "Content-Type: application/json" -d '{}'
```

### Expected Response

```json
{
  "status": "success",
  "mode": "production",
  "timestamp": "2024-01-01T12:00:00Z",
  "records_processed": 7728,
  "gcs_file": "gs://product-compliance-data-pmops-docai-dev-e93d/Product_Compliance_Infra_Data_20240101_120000.csv",
  "splunk_sent": true,
  "summary": {
    "total_records": 7728,
    "roadmap_items": 385,
    "unique_certifications": 28,
    "unique_products": 12
  }
}
```

## Step 6: Clean Up Test Resources (Optional)

```bash
# Delete test function
gcloud functions delete sharepoint-compliance-processor-test --region us-central1

# Delete seed generator
gcloud functions delete sharepoint-seed-generator --region us-central1

# Keep test secrets for rollback option
```

## Verification Checklist

- [ ] Real SharePoint credentials added to Secret Manager
- [ ] Production function deployed with `USE_SEED_DATA=false`
- [ ] Scheduler updated to use production function
- [ ] Manual test of production function successful
- [ ] Real data appears in Cloud Storage
- [ ] Splunk HEC receives data (if configured)
- [ ] Logs show successful SharePoint authentication
- [ ] First scheduled run completes successfully

## Troubleshooting

### "Authentication failed" Error

```bash
# Check secrets
gcloud secrets versions access sharepoint-compliance-client-secret --latest
gcloud secrets versions access sharepoint-compliance-tenant-id --latest

# Test with local script
cd sharepoint-integration
export SHAREPOINT_CLIENT_SECRET='your-real-secret'
export SHAREPOINT_TENANT_ID='your-real-tenant-id'
python process_sharepoint_data.py
```

### "No data from SharePoint" Error

```bash
# Check SharePoint connectivity
# Verify file name: "Product Compliance GTM Initiative Tracking-5.xlsx"
# Verify sheet name: "Compliance Inventory"
# Check SharePoint permissions for the app
```

### Function Timeout

```bash
# Increase timeout
gcloud functions deploy sharepoint-compliance-processor \
    --timeout 540s \
    --memory 1024MiB
```

## Rollback Plan

If production deployment fails:

```bash
# Rollback to test version
gcloud functions deploy sharepoint-compliance-processor \
    --source . \
    --entry-point process_sharepoint_compliance_test \
    --set-env-vars="USE_SEED_DATA=true"

# Update scheduler back to test function
TEST_URL=$(gcloud functions describe sharepoint-compliance-processor-test --region us-central1 --format='value(httpsUrl)')
gcloud scheduler jobs update sharepoint-compliance-scheduler \
    --uri "$TEST_URL" \
    --location us-central1
```

## Monitoring Production

### Key Metrics to Monitor

1. **Success Rate**: Should be >95%
2. **Processing Time**: <5 minutes per run
3. **Data Volume**: ~7,700 records per run
4. **Error Rate**: Should be 0%

### Alert Setup

```bash
# Create alert for high error rate
gcloud monitoring policies create \
    --notification-channels=projects/pmops-docai-dev-e93d/notificationChannels/EMAIL_CHANNEL_ID \
    --condition-filter='metric.type="cloudfunctions.googleapis.com/function/execution_count" resource.type="cloud_function" metric.label.status="error"' \
    --condition-threshold-value=5 \
    --condition-duration=300s
```

## Support Links

- **GCP Console**: https://console.cloud.google.com/home/dashboard?project=pmops-docai-dev-e93d
- **Cloud Functions**: https://console.cloud.google.com/functions/list?project=pmops-docai-dev-e93d
- **Secret Manager**: https://console.cloud.google.com/security/secret-manager?project=pmops-docai-dev-e93d
- **Cloud Storage**: https://console.cloud.google.com/storage/browser/product-compliance-data-pmops-docai-dev-e93d

## Next Steps

1. **Test production deployment thoroughly**
2. **Monitor first few scheduled runs**
3. **Set up alerts for failures**
4. **Document for team**
5. **Consider CI/CD for future updates**
