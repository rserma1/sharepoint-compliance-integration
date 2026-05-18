# Production Test Deployment Guide

This guide will help you deploy and test the SharePoint compliance integration with your real credentials.

## 📋 Prerequisites

You should have already added these secrets to GCP Secret Manager:
- ✅ `sharepoint-compliance-client-secret` - Your actual client secret
- ✅ `sharepoint-compliance-tenant-id` - Your actual tenant ID

The script will automatically create:
- ✅ `sharepoint-compliance-client-id` - Using the known client ID

## 🚀 Deployment Steps

### Option 1: Deploy via Cloud Shell (Recommended)

1. **Go to GCP Console**: https://console.cloud.google.com/?project=pmops-docai-dev-e93d

2. **Open Cloud Shell** (terminal icon in top right)

3. **Clone the repository**:
```bash
git clone https://github.com/rserma1/sharepoint-compliance-integration.git
cd sharepoint-compliance-integration/gcp
```

4. **Run the deployment script**:
```bash
chmod +x deploy-prod-test.sh
./deploy-prod-test.sh
```

5. **Wait for deployment** (takes 2-3 minutes)

### Option 2: Manual Deployment via Cloud Shell

If you prefer to run commands manually:

```bash
# Set project
gcloud config set project pmops-docai-dev-e93d

# Create client-id secret
echo "6f9ebeed-1c0c-4cdb-a7cb-19718966e3bc" | gcloud secrets create sharepoint-compliance-client-id --data-file=-

# Deploy function
cd sharepoint-compliance-integration/gcp
cp main_prod_test.py main.py

gcloud functions deploy sharepoint-compliance-prod-test \
  --runtime=python311 \
  --region=us-central1 \
  --source=. \
  --entry-point=process_sharepoint_compliance_test \
  --trigger-http \
  --allow-unauthenticated \
  --timeout=540s \
  --memory=1024MiB \
  --set-env-vars="GCP_PROJECT=pmops-docai-dev-e93d,GCS_BUCKET=product-compliance-data-pmops-docai-dev-e93d,SECRET_PREFIX=sharepoint-compliance"
```

## 🧪 Testing the Function

### Test via curl

After deployment, you'll get a function URL. Test it with:

```bash
# Get the function URL
FUNCTION_URL=$(gcloud functions describe sharepoint-compliance-prod-test --region=us-central1 --format='value(httpsTrigger.url)')

# Test the function
curl -X POST $FUNCTION_URL
```

### Expected Response

If successful, you should see:

```json
{
  "status": "success",
  "message": "SharePoint compliance data processed successfully",
  "timestamp": "2026-05-18T18:30:00.000000",
  "source": {
    "file": "Product Compliance GTM Initiative Tracking.xlsx",
    "worksheet": "Compliance Inventory",
    "site_id": "splunk.sharepoint.com,..."
  },
  "data": {
    "rows_retrieved": 7504,
    "rows_transformed": 7504,
    "columns": ["Product", "Feature", "Product_Area", ...]
  },
  "output": {
    "bucket": "product-compliance-data-pmops-docai-dev-e93d",
    "filename": "Product_Compliance_Infra_Data_20260518_183000.csv",
    "gcs_uri": "gs://product-compliance-data-pmops-docai-dev-e93d/Product_Compliance_Infra_Data_20260518_183000.csv"
  }
}
```

## 📊 Verify the Results

### Check Cloud Storage

```bash
# List files in the bucket
gsutil ls gs://product-compliance-data-pmops-docai-dev-e93d

# Download the latest file
gsutil cp gs://product-compliance-data-pmops-docai-dev-e93d/Product_Compliance_Infra_Data_*.csv ./latest.csv

# View first 10 lines
head -10 latest.csv
```

### Check Function Logs

```bash
# View recent logs
gcloud functions logs read sharepoint-compliance-prod-test --region=us-central1 --limit=50

# Follow logs in real-time
gcloud functions logs read sharepoint-compliance-prod-test --region=us-central1 --limit=50 --follow
```

## 🔧 Configuration

### SharePoint Configuration

The function is configured to pull from:
- **File**: `Product Compliance GTM Initiative Tracking.xlsx`
- **Worksheet**: `Compliance Inventory`
- **Site ID**: `splunk.sharepoint.com,d4e8c5b6-7a9f-4e3d-8c2b-1a5e6f7d8c9a,a1b2c3d4-e5f6-7890-abcd-ef1234567890`

If you need to change these, edit `main_prod_test.py`:

```python
SHAREPOINT_SITE_ID = "your-site-id"
FILE_NAME = "your-file-name.xlsx"
WORKSHEET_NAME = "your-worksheet-name"
```

### Update Site ID

If you don't have the correct Site ID, you can find it:

```bash
# Get access token (in Cloud Shell)
# Then use Graph API Explorer or run:
curl -X GET "https://graph.microsoft.com/v1.0/sites/splunk.sharepoint.com:/sites/YourSiteName" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## 🐛 Troubleshooting

### Error: "Secret not found"

Make sure you've created all required secrets:
```bash
gcloud secrets list | grep sharepoint-compliance
```

You should see:
- sharepoint-compliance-client-id
- sharepoint-compliance-client-secret
- sharepoint-compliance-tenant-id

### Error: "File not found"

Check the file name and make sure it exists in SharePoint:
- Verify the exact file name (case-sensitive)
- Check that the file is in the root of the document library
- Verify you have permissions to access the file

### Error: "Worksheet not found"

Check the worksheet name:
- Verify the exact worksheet name (case-sensitive)
- Make sure the worksheet exists in the Excel file
- Check for any special characters or spaces

### Error: "Unauthorized" or "Access denied"

Check your credentials:
```bash
# Verify secrets exist and have values
gcloud secrets versions access latest --secret=sharepoint-compliance-client-id
gcloud secrets versions access latest --secret=sharepoint-compliance-tenant-id
# Don't print client-secret for security
```

Make sure your Azure AD app has:
- **API Permissions**: `Sites.Read.All`, `Files.Read.All`
- **Grant Type**: Client credentials
- **Admin consent**: Granted

## 📝 Next Steps

Once the test function works:

1. **Verify data quality** - Check the CSV output matches expectations
2. **Set up Cloud Scheduler** - Automate daily runs
3. **Add Splunk integration** - Send data to Splunk HEC
4. **Monitor and alert** - Set up error notifications

## 🔗 Useful Links

- **GCP Console**: https://console.cloud.google.com/?project=pmops-docai-dev-e93d
- **Cloud Functions**: https://console.cloud.google.com/functions/list?project=pmops-docai-dev-e93d
- **Secret Manager**: https://console.cloud.google.com/security/secret-manager?project=pmops-docai-dev-e93d
- **Cloud Storage**: https://console.cloud.google.com/storage/browser/product-compliance-data-pmops-docai-dev-e93d
- **Logs**: https://console.cloud.google.com/logs/query?project=pmops-docai-dev-e93d

## 📞 Support

If you encounter issues:
1. Check the function logs for detailed error messages
2. Verify all secrets are correctly set
3. Test SharePoint access manually using Graph Explorer
4. Check Azure AD app permissions and consent
