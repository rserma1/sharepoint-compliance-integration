"""
Production Test GCP Cloud Function for SharePoint Excel Data
Pulls data from "Compliance Inventory" tab and transforms to CSV
"""

import functions_framework
import json
import logging
import os
from datetime import datetime
from google.cloud import secretmanager
from google.cloud import storage
import pandas as pd
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
PROJECT_ID = os.environ.get('GCP_PROJECT', 'pmops-docai-dev-e93d')
BUCKET_NAME = os.environ.get('GCS_BUCKET', 'product-compliance-data-pmops-docai-dev-e93d')
SECRET_PREFIX = os.environ.get('SECRET_PREFIX', 'sharepoint-compliance')

# SharePoint configuration
SHAREPOINT_SITE_ID = "splunk.sharepoint.com,d4e8c5b6-7a9f-4e3d-8c2b-1a5e6f7d8c9a,a1b2c3d4-e5f6-7890-abcd-ef1234567890"
FILE_NAME = "Product Compliance GTM Initiative Tracking.xlsx"
WORKSHEET_NAME = "Compliance Inventory"


def get_secret(secret_id: str) -> str:
    """Retrieve secret from Secret Manager"""
    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{PROJECT_ID}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode('UTF-8')
    except Exception as e:
        logger.error(f"Error retrieving secret {secret_id}: {e}")
        raise


def get_access_token(client_id: str, client_secret: str, tenant_id: str) -> str:
    """Get Microsoft Graph API access token"""
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    
    data = {
        'client_id': client_id,
        'client_secret': client_secret,
        'scope': 'https://graph.microsoft.com/.default',
        'grant_type': 'client_credentials'
    }
    
    response = requests.post(token_url, data=data)
    response.raise_for_status()
    return response.json()['access_token']


def get_file_id(access_token: str, site_id: str, file_name: str) -> str:
    """Get the file ID for the Excel file"""
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json'
    }
    
    # Search for the file
    search_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root/search(q='{file_name}')"
    response = requests.get(search_url, headers=headers)
    response.raise_for_status()
    
    results = response.json().get('value', [])
    if not results:
        raise ValueError(f"File not found: {file_name}")
    
    return results[0]['id']


def get_worksheet_data(access_token: str, site_id: str, file_id: str, worksheet_name: str) -> pd.DataFrame:
    """Get data from specific worksheet"""
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json'
    }
    
    # Get worksheet data
    worksheet_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/items/{file_id}/workbook/worksheets('{worksheet_name}')/usedRange"
    response = requests.get(worksheet_url, headers=headers)
    response.raise_for_status()
    
    data = response.json()
    values = data.get('values', [])
    
    if not values:
        raise ValueError(f"No data found in worksheet: {worksheet_name}")
    
    # First row is headers
    headers_row = values[0]
    data_rows = values[1:]
    
    # Create DataFrame
    df = pd.DataFrame(data_rows, columns=headers_row)
    
    logger.info(f"Retrieved {len(df)} rows from worksheet '{worksheet_name}'")
    return df


def transform_to_compliance_format(df: pd.DataFrame) -> pd.DataFrame:
    """Transform data to compliance CSV format"""
    
    # Expected columns from the Compliance Inventory tab
    column_mapping = {
        'Product': 'Product',
        'Feature': 'Feature',
        'Product Area': 'Product_Area',
        'Infrastructure': 'Infrastructure',
        'Region': 'Region',
        'Category': 'Category',
        'Subcategory': 'Subcategory',
        'Certification': 'Certification',
        'Compliance Status': 'Compliance_Status',
        'Roadmap Quarter': 'Roadmap_Quarter',
        'Additional Information (Notes)': 'Notes'
    }
    
    # Rename columns
    transformed_df = df.copy()
    
    # Only keep columns that exist in the mapping
    existing_columns = [col for col in column_mapping.keys() if col in transformed_df.columns]
    transformed_df = transformed_df[existing_columns]
    
    # Rename to standard format
    transformed_df = transformed_df.rename(columns={k: column_mapping[k] for k in existing_columns})
    
    # Fill NaN values with empty strings
    transformed_df = transformed_df.fillna('')
    
    # Add metadata
    transformed_df['Last_Updated'] = datetime.utcnow().isoformat()
    transformed_df['Source'] = 'SharePoint'
    
    logger.info(f"Transformed data: {len(transformed_df)} rows, {len(transformed_df.columns)} columns")
    return transformed_df


def upload_to_gcs(df: pd.DataFrame, bucket_name: str) -> str:
    """Upload DataFrame to Google Cloud Storage as CSV"""
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        
        # Generate filename with timestamp
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        filename = f'Product_Compliance_Infra_Data_{timestamp}.csv'
        
        # Convert to CSV
        csv_data = df.to_csv(index=False)
        
        # Upload to GCS
        blob = bucket.blob(filename)
        blob.upload_from_string(csv_data, content_type='text/csv')
        
        logger.info(f"✅ Uploaded to GCS: gs://{bucket_name}/{filename}")
        return filename
    except Exception as e:
        logger.error(f"Error uploading to GCS: {e}")
        raise


@functions_framework.http
def process_sharepoint_compliance_test(request):
    """HTTP Cloud Function to process SharePoint compliance data"""
    
    logger.info("🚀 Starting SharePoint compliance data processing (PRODUCTION TEST)...")
    
    try:
        # Get credentials from Secret Manager
        logger.info("📋 Retrieving credentials from Secret Manager...")
        client_id = get_secret(f'{SECRET_PREFIX}-client-id')
        client_secret = get_secret(f'{SECRET_PREFIX}-client-secret')
        tenant_id = get_secret(f'{SECRET_PREFIX}-tenant-id')
        
        logger.info(f"✅ Retrieved credentials for client: {client_id[:8]}...")
        
        # Get access token
        logger.info("🔑 Getting Microsoft Graph API access token...")
        access_token = get_access_token(client_id, client_secret, tenant_id)
        logger.info("✅ Access token obtained")
        
        # Get file ID
        logger.info(f"📁 Searching for file: {FILE_NAME}...")
        file_id = get_file_id(access_token, SHAREPOINT_SITE_ID, FILE_NAME)
        logger.info(f"✅ Found file ID: {file_id[:20]}...")
        
        # Get worksheet data
        logger.info(f"📊 Reading worksheet: {WORKSHEET_NAME}...")
        df = get_worksheet_data(access_token, SHAREPOINT_SITE_ID, file_id, WORKSHEET_NAME)
        logger.info(f"✅ Retrieved {len(df)} rows from SharePoint")
        
        # Transform data
        logger.info("🔄 Transforming data to compliance format...")
        transformed_df = transform_to_compliance_format(df)
        logger.info(f"✅ Transformed {len(transformed_df)} records")
        
        # Upload to GCS
        logger.info(f"☁️ Uploading to Cloud Storage: {BUCKET_NAME}...")
        filename = upload_to_gcs(transformed_df, BUCKET_NAME)
        logger.info(f"✅ Upload complete: {filename}")
        
        # Prepare response
        response_data = {
            'status': 'success',
            'message': 'SharePoint compliance data processed successfully',
            'timestamp': datetime.utcnow().isoformat(),
            'source': {
                'file': FILE_NAME,
                'worksheet': WORKSHEET_NAME,
                'site_id': SHAREPOINT_SITE_ID
            },
            'data': {
                'rows_retrieved': len(df),
                'rows_transformed': len(transformed_df),
                'columns': list(transformed_df.columns)
            },
            'output': {
                'bucket': BUCKET_NAME,
                'filename': filename,
                'gcs_uri': f'gs://{BUCKET_NAME}/{filename}'
            }
        }
        
        logger.info("🎉 Processing complete!")
        return json.dumps(response_data, indent=2), 200, {'Content-Type': 'application/json'}
        
    except Exception as e:
        logger.error(f"❌ Error processing SharePoint data: {e}")
        error_response = {
            'status': 'error',
            'message': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }
        return json.dumps(error_response, indent=2), 500, {'Content-Type': 'application/json'}
