# GCP Architecture for SharePoint Integration

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
                                │
                                ▼
                       ┌──────────────────┐
                       │  Cloud Logging   │
                       │  (Monitoring)    │
                       └──────────────────┘
```

## Components

### 1. **Cloud Scheduler** (Automation)
- **Purpose**: Trigger the data processing on a schedule (daily, hourly, etc.)
- **Configuration**: HTTP trigger to Cloud Function
- **Benefits**: Serverless, cost-effective, reliable scheduling

### 2. **Cloud Functions** (Main Processing)
- **Purpose**: Execute the SharePoint data processing logic
- **Runtime**: Python 3.9+
- **Memory**: 512MB - 1GB (configurable)
- **Timeout**: 9 minutes (max)
- **Triggers**: HTTP (from Scheduler) or Pub/Sub

### 3. **Secret Manager** (Security)
- **Purpose**: Store sensitive credentials securely
- **Secrets**:
  - `SHAREPOINT_CLIENT_SECRET`
  - `SHAREPOINT_TENANT_ID`
  - `SPLUNK_HEC_TOKEN` (optional)
  - `SPLUNK_HOST` (optional)
- **Benefits**: Encrypted storage, automatic rotation, audit logs

### 4. **Cloud Storage** (Data Storage)
- **Purpose**: Store processed CSV files
- **Bucket**: `product-compliance-data-{project-id}`
- **Lifecycle**: Auto-delete old files (optional)
- **Access**: Private with service account access

### 5. **Cloud Logging** (Monitoring)
- **Purpose**: Centralized logging and monitoring
- **Integration**: Automatic from Cloud Functions
- **Alerts**: Error notifications via Cloud Monitoring

### 6. **Cloud Run** (Alternative Option)
- **Purpose**: Container-based deployment for longer processing
- **Use Case**: If processing takes >9 minutes
- **Benefits**: Longer timeout, custom runtime, scaling

## Deployment Options

### Option 1: Cloud Functions (Recommended)
- **Best for**: Quick processing (<9 minutes)
- **Cost**: Pay-per-invocation (~$0.0000002 per invocation)
- **Setup**: Simple, serverless

### Option 2: Cloud Run (Advanced)
- **Best for**: Complex processing (>9 minutes)
- **Cost**: Pay-per-request (~$0.000025 per request)
- **Setup**: Container-based, more control

## Security Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Service        │───▶│  Secret Manager  │───▶│  SharePoint     │
│  Account        │    │  (Encrypted)    │    │  OAuth 2.0      │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  IAM Roles      │    │  Access Control  │    │  API Permissions│
│  (Least Priv)   │    │  (Fine-grained)  │    │  (Minimal)      │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## Cost Estimation

### Monthly Costs (Approximate)
- **Cloud Functions**: $0.10 - $1.00 (daily runs)
- **Cloud Storage**: $0.02 - $0.05 (CSV storage)
- **Secret Manager**: $0.03 (per secret)
- **Cloud Logging**: $0.50 (log retention)
- **Cloud Scheduler**: $0.03 (monthly job)
- **Total**: ~$0.68 - $1.61 per month

### Variables
- **Frequency**: Daily vs hourly runs
- **Data Volume**: Size of Excel files
- **Storage**: Retention period for CSVs
- **Logging**: Log retention period

## Data Flow

1. **Trigger**: Cloud Scheduler fires HTTP request
2. **Authentication**: Cloud Function gets secrets from Secret Manager
3. **Download**: Function connects to SharePoint via Microsoft Graph API
4. **Process**: Parse Excel, transform data to compliance format
5. **Store**: Save CSV to Cloud Storage
6. **Optional**: Send data to Splunk via HEC
7. **Log**: Write logs to Cloud Logging
8. **Monitor**: Cloud Monitoring tracks metrics and errors

## High Availability & Reliability

### Reliability Features
- **Automatic Retries**: Built into Cloud Functions
- **Dead Letter Queue**: Failed events to Pub/Sub
- **Health Checks**: Cloud Monitoring alerts
- **Regional Deployment**: Multi-region options

### Backup & Recovery
- **Cloud Storage**: Automatic replication
- **Secret Manager**: Multi-region replication
- **Logs**: Immutable audit trail
- **Code**: Version control in Cloud Source Repositories

## Monitoring & Observability

### Metrics to Track
- **Success Rate**: % of successful processing runs
- **Processing Time**: Duration of each run
- **Data Volume**: Records processed per run
- **Error Rate**: Types and frequency of errors
- **API Calls**: SharePoint and Splunk API usage

### Alerting
- **Processing Failures**: Immediate email/Slack alerts
- **Performance Issues**: Slow processing warnings
- **Credential Issues**: Authentication failure alerts
- **Data Quality**: Missing or malformed data alerts

## Deployment Strategy

### Phase 1: Basic Setup
1. Create GCP project
2. Enable required APIs
3. Create service account
4. Set up Secret Manager
5. Deploy Cloud Function
6. Configure Cloud Scheduler

### Phase 2: Enhanced Features
1. Add Splunk HEC integration
2. Implement error handling
3. Set up monitoring and alerts
4. Add data validation
5. Create dashboard

### Phase 3: Advanced Features
1. Multi-region deployment
2. Data versioning
3. Advanced error recovery
4. Performance optimization
5. Cost optimization

## Required GCP APIs

```bash
# Enable these APIs before deployment
gcloud services enable \
  cloudfunctions.googleapis.com \
  cloudscheduler.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com
```

## Next Steps

1. **Choose deployment option** (Cloud Functions vs Cloud Run)
2. **Set up GCP project** and enable APIs
3. **Create service account** with proper permissions
4. **Configure secrets** in Secret Manager
5. **Deploy and test** the solution
6. **Set up monitoring** and alerts
7. **Schedule automated runs**
