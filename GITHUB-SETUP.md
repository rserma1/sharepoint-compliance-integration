# GitHub Repository Setup for SharePoint Compliance Integration

## Step 1: Create GitHub Repository

### Option A: Create via GitHub CLI
```bash
# Navigate to the sharepoint-integration directory
cd sharepoint-integration

# Initialize git repository
git init
git add .
git commit -m "Initial commit: SharePoint compliance integration with test deployment"

# Create GitHub repository
gh repo create sharepoint-compliance-integration --public --push --source=.
```

### Option B: Create via GitHub Web UI
1. Go to https://github.com/new
2. Repository name: `sharepoint-compliance-integration`
3. Description: `SharePoint compliance data integration with GCP deployment`
4. Make it Public
5. Don't initialize with README (we already have files)
6. Click "Create repository"
7. Follow the instructions to push existing files

## Step 2: Set Up GitHub Secrets

### Required Secrets

Go to your GitHub repository → Settings → Secrets and variables → Actions → New repository secret

#### 1. GCP_SA_KEY (Required)
```bash
# Create service account key for GitHub
gcloud iam service-accounts keys create ~/github-key.json \
    --iam-account sharepoint-compliance-processor@pmops-docai-dev-e93d.iam.gserviceaccount.com

# Copy the content of the key file
cat ~/github-key.json
```

Add this as the `GCP_SA_KEY` secret in GitHub.

#### 2. Optional Secrets (for future production use)
- `SHAREPOINT_CLIENT_SECRET` - SharePoint client secret
- `SHAREPOINT_TENANT_ID` - SharePoint tenant ID
- `SPLUNK_HOST` - Splunk host (e.g., your-stack.splunkcloud.com)
- `SPLUNK_HEC_TOKEN` - Splunk HEC token

## Step 3: Push to GitHub

```bash
# Add all files
git add .
git commit -m "Add complete SharePoint compliance integration"

# Add remote and push
git remote add origin https://github.com/YOUR_USERNAME/sharepoint-compliance-integration.git
git push -u origin main
```

## Step 4: Run GitHub Actions Deployment

### Option A: Manual Trigger
1. Go to your GitHub repository
2. Click "Actions" tab
3. Select "Deploy SharePoint Compliance Processor (TEST)" workflow
4. Click "Run workflow"
5. Choose:
   - `deploy_mode`: test
   - `use_seed_data`: true
   - `num_records`: 100
6. Click "Run workflow"

### Option B: Automatic Trigger
The workflow will automatically run when you push to the main branch.

## Step 5: Monitor Deployment

### Check GitHub Actions
- Go to the "Actions" tab
- Click on the running workflow
- Monitor the deployment progress

### Expected Output
The workflow will output:
- Function URLs
- GCP Console links
- Test results
- Management commands

## Step 6: Test Deployed Functions

### Test Main Function
```bash
# Get function URL from workflow output
FUNCTION_URL="https://us-central1-pmops-docai-dev-e93d.cloudfunctions.net/sharepoint-compliance-processor-test"

# Test the function
curl -X POST "$FUNCTION_URL" -H "Content-Type: application/json" -d '{}'
```

### Test Seed Generator
```bash
# Get seed generator URL from workflow output
SEED_URL="https://us-central1-pmops-docai-dev-e93d.cloudfunctions.net/sharepoint-seed-generator"

# Generate custom seed data
curl -X POST "$SEED_URL" -H "Content-Type: application/json" -d '{"num_records": 50}'
```

## Step 7: Verify Results

### Check Cloud Storage
```bash
# List files in GCS bucket
gsutil ls gs://product-compliance-data-pmops-docai-dev-e93d

# Download and view a sample file
gsutil cp gs://product-compliance-data-pmops-docai-dev-e93d/Product_Compliance_Infra_Data_*.csv sample.csv
head -10 sample.csv
```

### Check Cloud Functions
```bash
# List deployed functions
gcloud functions list --filter="name~sharepoint"

# View logs
gcloud functions logs read sharepoint-compliance-processor-test --region us-central1 --limit 50
```

## Troubleshooting

### Common Issues

#### "GCP_SA_KEY not found"
- Make sure the service account key is correctly added as a GitHub secret
- Check that the secret name is exactly `GCP_SA_KEY`

#### "Permission denied"
- Ensure the service account has the required IAM roles
- Check that the service account exists: `gcloud iam service-accounts list`

#### "Function deployment failed"
- Check the GitHub Actions logs for detailed error messages
- Verify the function code has no syntax errors

#### "Function timeout"
- The test function may take a few minutes to cold start
- Try running it again after a few minutes

### Debug Commands
```bash
# Check service account permissions
gcloud projects get-iam-policy pmops-docai-dev-e93d --flatten="bindings[].members" --format="table(bindings.role, bindings.members)"

# Test local function
cd sharepoint-integration/gcp
python main_test.py

# Check GCP logs
gcloud logging read "resource.type=cloud_function" --limit 10 --format="table(timestamp,textPayload)"
```

## Next Steps

### After Test Deployment Works

1. **Verify data quality** - Check that the CSV files contain the expected data
2. **Test scheduler** - Verify the daily scheduler works correctly
3. **Set up alerts** - Configure error notifications
4. **Plan production upgrade** - Follow the `UPDATE-CREDENTIALS.md` guide

### For Production Use

1. **Get real SharePoint credentials** from your Azure AD administrator
2. **Update GCP secrets** with real values
3. **Deploy production version** using the production workflow
4. **Monitor first few runs** to ensure everything works correctly

## Repository Structure

```
sharepoint-integration/
├── .github/workflows/
│   ├── deploy-test.yml          # Test deployment workflow
│   └── deploy-gcp.yml           # Production deployment workflow
├── gcp/
│   ├── main_test.py              # Test Cloud Function
│   ├── main.py                   # Production Cloud Function
│   ├── requirements.txt          # Python dependencies
│   ├── Dockerfile               # Container deployment
│   ├── deploy.sh                # Deployment script
│   ├── quick-deploy.sh          # Quick deployment script
│   ├── monitoring.yaml          # Monitoring configuration
│   ├── seed_data_current.py     # Current dataset loader
│   └── Product_Compliance_Infra_Data.csv  # Current dataset
├── sharepoint_client.py         # SharePoint API client
├── splunk_client.py             # Splunk HEC client
├── config.py                    # Configuration
├── process_sharepoint_data.py   # Local processing script
├── test_connection.py           # SharePoint connection test
├── test_splunk_hec.py          # Splunk HEC test
├── requirements.txt            # Local dependencies
├── .env.example                # Environment variables template
├── .gitignore                  # Git ignore rules
├── README.md                   # Main documentation
├── QUICKSTART.md               # Quick start guide
├── gcp-architecture.md         # GCP architecture docs
├── deploy-pmops.md             # Project-specific deployment guide
├── UPDATE-CREDENTIALS.md       # Production upgrade guide
└── GITHUB-SETUP.md             # This file
```

## Support

If you encounter any issues:

1. **Check GitHub Actions logs** - Detailed error messages
2. **Check GCP Console** - Function logs and error details
3. **Review this guide** - Ensure all steps were followed
4. **Test locally** - Use the local test scripts to debug

## Success Criteria

✅ **Successful Deployment Indicators:**
- GitHub Actions workflow completes successfully
- Cloud Functions are deployed and accessible
- Test data appears in Cloud Storage
- Function tests return success responses
- Scheduler job is created and enabled
- No error messages in logs

Once you see these indicators, your SharePoint compliance integration is ready for production use!
