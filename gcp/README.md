# GCP SharePoint Compliance Integration

This directory contains the Google Cloud Platform deployment configuration for the SharePoint compliance data processing solution.

## Architecture Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Cloud Scheduler│───▶│  Cloud Function   │───▶│  SharePoint API │
│   (Cron Job)    │    │  (Data Processor) │    │  (Microsoft)    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │  Cloud Storage   │
                       │ (CSV Files)     │
                       └──────────────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │  Splunk HEC      │
                       │  (Optional)      │
                       └──────────────────┘
```

## Files

- **`main.py`** - Cloud Function implementation
- **`requirements.txt`** - Python dependencies
- **`Dockerfile`** - Container configuration for Cloud Run
- **`deploy.sh`** - Automated deployment script
- **`monitoring.yaml`** - Monitoring and alerting configuration

## Quick Start

### 1. Prerequisites

```bash
# Install gcloud CLI and authenticate
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Enable required APIs
gcloud services enable \
    cloudfunctions.googleapis.com \
    cloudscheduler.googleapis.com \
    secretmanager.googleapis.com \
    storage.googleapis.com \
    cloudbuild.googleapis.com
```

### 2. Deploy

```bash
cd gcp
./deploy.sh
```

The script will:
- Enable required APIs
- Create service account with proper permissions
- Set up Cloud Storage bucket
- Configure secrets in Secret Manager
- Deploy Cloud Function
- Create Cloud Scheduler job
- Test the deployment

### 3. Configure Secrets

During deployment, you'll be prompted for:
- SharePoint Client Secret
- SharePoint Tenant ID
- Splunk Host (optional)
- Splunk HEC Token (optional)

## Configuration

### Environment Variables

- `GCP_PROJECT` - GCP project ID
- `GCS_BUCKET` - Cloud Storage bucket name
- `SECRET_PREFIX` - Prefix for secret names
- `REGION` - Deployment region (default: us-central1)

### Cloud Function Settings

- **Runtime**: Python 3.9
- **Memory**: 1024MiB
- **Timeout**: 540s (9 minutes)
- **Trigger**: HTTP (from Cloud Scheduler)

### Schedule

Default: Daily at 6 AM UTC (`0 6 * * *`)

To modify:
```bash
gcloud scheduler jobs update sharepoint-compliance-processor-scheduler \
    --schedule "0 8 * * *"  # 8 AM UTC
```

## Deployment Options

### Option 1: Cloud Functions (Recommended)

```bash
# Deploy as Cloud Function
./deploy.sh
```

**Benefits:**
- Serverless, pay-per-invocation
- Automatic scaling
- Integrated logging and monitoring
- Cost-effective for daily runs

### Option 2: Cloud Run (Advanced)

```bash
# Build and deploy to Cloud Run
gcloud builds submit --tag gcr.io/$PROJECT_ID/sharepoint-compliance-processor .
gcloud run deploy sharepoint-compliance-processor \
    --image gcr.io/$PROJECT_ID/sharepoint-compliance-processor \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated \
    --memory 1Gi \
    --timeout 15m
```

**Benefits:**
- Longer timeout (up to 15 minutes)
- More control over runtime
- Better for complex processing

## Monitoring

### Dashboard

View the custom dashboard in Cloud Monitoring:
```
https://console.cloud.google.com/monitoring/dashboards
```

### Alerts

Default alerts configured:
- High error rate (>5 errors in 5 minutes)
- Processing failures
- Long processing time (>5 minutes)

### Logs

View logs:
```bash
# Real-time logs
gcloud functions logs read sharepoint-compliance-processor --region $REGION --limit 50

# Follow logs
gcloud functions logs read sharepoint-compliance-processor --region $REGION --tail
```

## Manual Testing

### Test Cloud Function

```bash
# Get function URL
FUNCTION_URL=$(gcloud functions describe sharepoint-compliance-processor --region $REGION --format='value(httpsUrl)')

# Test manually
curl -X POST "$FUNCTION_URL" -H "Content-Type: application/json" -d '{}'
```

### Test Cloud Run

```bash
# Get service URL
SERVICE_URL=$(gcloud run services describe sharepoint-compliance-processor --region $REGION --format='value(status.url)')

# Test manually
curl -X POST "$SERVICE_URL" -H "Content-Type: application/json" -d '{}'
```

## Data Flow

1. **Trigger**: Cloud Scheduler calls Cloud Function
2. **Authentication**: Get credentials from Secret Manager
3. **Download**: Fetch Excel from SharePoint
4. **Process**: Parse and transform data
5. **Store**: Upload CSV to Cloud Storage
6. **Optional**: Send to Splunk HEC
7. **Log**: Write metrics to Cloud Logging

## Cost Estimation

### Monthly Costs (Approximate)

- **Cloud Functions**: $0.10 - $1.00 (daily runs)
- **Cloud Storage**: $0.02 - $0.05 (CSV storage)
- **Secret Manager**: $0.03 (per secret)
- **Cloud Logging**: $0.50 (log retention)
- **Cloud Scheduler**: $0.03 (monthly job)
- **Total**: ~$0.68 - $1.61 per month

## Security

### Service Account Permissions

- `roles/secretmanager.secretAccessor` - Access secrets
- `roles/storage.objectAdmin` - Read/write Cloud Storage
- `roles/logging.logWriter` - Write logs
- `roles/monitoring.metricWriter` - Write metrics

### Secret Manager

All sensitive data stored in Secret Manager:
- SharePoint Client Secret
- SharePoint Tenant ID
- Splunk HEC Token (optional)
- Splunk Host (optional)

### Network Security

- HTTPS-only endpoints
- VPC-Connector for private connections (optional)
- IAM-based access control

## Troubleshooting

### Common Issues

#### "Authentication failed"
```bash
# Check secrets
gcloud secrets versions list sharepoint-compliance-client-secret
gcloud secrets versions list sharepoint-compliance-tenant-id

# Test access
gcloud secrets versions access sharepoint-compliance-client-secret --latest
```

#### "Function timeout"
```bash
# Increase timeout
gcloud functions deploy sharepoint-compliance-processor \
    --timeout 540s \
    --memory 1024MiB
```

#### "Storage permission denied"
```bash
# Check bucket permissions
gsutil iam get gs://$BUCKET_NAME

# Grant permissions
gsutil iam ch serviceAccount:$SERVICE_ACCOUNT:objectAdmin gs://$BUCKET_NAME
```

### Debug Mode

Enable debug logging:
```bash
gcloud functions deploy sharepoint-compliance-processor \
    --set-env-vars="DEBUG=true"
```

## Maintenance

### Regular Tasks

1. **Monitor logs** for errors or warnings
2. **Check storage** for old files (optional cleanup)
3. **Update secrets** when they expire
4. **Review costs** and optimize as needed
5. **Update dependencies** for security patches

### Backup and Recovery

- **Code**: Version control in Git
- **Configuration**: Infrastructure as code
- **Data**: Automatic Cloud Storage replication
- **Secrets**: Multi-region Secret Manager replication

## Support

### Logs and Monitoring

- **Cloud Logging**: All execution logs
- **Cloud Monitoring**: Custom metrics and dashboards
- **Error Reporting**: Automatic error tracking
- **Alerts**: Email notifications for failures

### Documentation

- [GCP Cloud Functions Documentation](https://cloud.google.com/functions/docs)
- [GCP Secret Manager Documentation](https://cloud.google.com/secret-manager/docs)
- [GCP Cloud Scheduler Documentation](https://cloud.google.com/scheduler/docs)

## Next Steps

1. **Deploy** the solution using `./deploy.sh`
2. **Monitor** the first few executions
3. **Configure** alerts for your team
4. **Optimize** based on usage patterns
5. **Scale** to additional regions if needed
