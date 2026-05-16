"""
GCP Cloud Function for SharePoint Compliance Data Processing
"""

import functions_framework
import os
import json
import logging
from datetime import datetime, timezone
from google.cloud import storage
from google.cloud import secretmanager
import pandas as pd
import requests
import msal
import io
from typing import Dict, List, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
PROJECT_ID = os.environ.get('GCP_PROJECT')
BUCKET_NAME = os.environ.get('GCS_BUCKET', f'product-compliance-data-{PROJECT_ID}')
SECRET_PREFIX = os.environ.get('SECRET_PREFIX', 'sharepoint-compliance')


def access_secret_version(project_id: str, secret_id: str, version_id: str = "latest") -> str:
    """Access secret version from Secret Manager"""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")


def get_credentials() -> Dict[str, str]:
    """Get credentials from Secret Manager"""
    try:
        credentials = {}
        
        # SharePoint credentials
        credentials['client_id'] = '6f9ebeed-1c0c-4cdb-a7cb-19718966e3bc'
        credentials['client_secret'] = access_secret_version(PROJECT_ID, f'{SECRET_PREFIX}-client-secret')
        credentials['tenant_id'] = access_secret_version(PROJECT_ID, f'{SECRET_PREFIX}-tenant-id')
        
        # Optional Splunk credentials
        try:
            credentials['splunk_host'] = access_secret_version(PROJECT_ID, f'{SECRET_PREFIX}-splunk-host')
            credentials['splunk_token'] = access_secret_version(PROJECT_ID, f'{SECRET_PREFIX}-splunk-token')
        except Exception:
            logger.info("Splunk credentials not found - HEC integration disabled")
            credentials['splunk_host'] = None
            credentials['splunk_token'] = None
        
        return credentials
        
    except Exception as e:
        logger.error(f"Error accessing secrets: {str(e)}")
        raise


class SharePointGCPClient:
    """SharePoint client optimized for GCP Cloud Functions"""
    
    def __init__(self, credentials: Dict[str, str]):
        self.client_id = credentials['client_id']
        self.client_secret = credentials['client_secret']
        self.tenant_id = credentials['tenant_id']
        self.access_token = None
        self.site_id = None
    
    def authenticate(self) -> bool:
        """Authenticate with Microsoft Graph API"""
        try:
            authority = f"https://login.microsoftonline.com/{self.tenant_id}"
            app = msal.ConfidentialClientApplication(
                self.client_id,
                authority=authority,
                client_credential=self.client_secret,
            )
            
            result = app.acquire_token_for_client(scopes=['https://graph.microsoft.com/.default'])
            
            if "access_token" in result:
                self.access_token = result['access_token']
                logger.info("✅ SharePoint authentication successful")
                return True
            else:
                logger.error(f"❌ SharePoint authentication failed: {result.get('error_description', 'Unknown error')}")
                return False
                
        except Exception as e:
            logger.error(f"❌ SharePoint authentication error: {str(e)}")
            return False
    
    def get_site_id(self, site_url: str) -> Optional[str]:
        """Get SharePoint site ID"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(site_url)
            hostname = parsed.netloc
            site_path = parsed.path
            
            endpoint = f"https://graph.microsoft.com/v1.0/sites/{hostname}:{site_path}"
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Accept': 'application/json'
            }
            
            response = requests.get(endpoint, headers=headers, timeout=30)
            
            if response.status_code == 200:
                site_data = response.json()
                self.site_id = site_data['id']
                logger.info(f"✅ Site ID retrieved: {self.site_id}")
                return self.site_id
            else:
                logger.error(f"❌ Failed to get site ID: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error getting site ID: {str(e)}")
            return None
    
    def download_excel(self, file_name: str) -> Optional[bytes]:
        """Download Excel file from SharePoint"""
        try:
            if not self.site_id:
                return None
            
            endpoint = f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drive/root:/{file_name}:/content"
            headers = {'Authorization': f'Bearer {self.access_token}'}
            
            response = requests.get(endpoint, headers=headers, timeout=30)
            
            if response.status_code == 200:
                logger.info(f"✅ File downloaded: {file_name} ({len(response.content)} bytes)")
                return response.content
            else:
                logger.error(f"❌ Failed to download file: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error downloading file: {str(e)}")
            return None


def process_excel_data(excel_content: bytes) -> pd.DataFrame:
    """Process Excel data and return compliance DataFrame"""
    try:
        # Read Excel from bytes
        excel_file = io.BytesIO(excel_content)
        df = pd.read_excel(
            excel_file, 
            sheet_name='Compliance Inventory', 
            skiprows=3,
            keep_default_na=False,
            na_values=['']
        )
        
        logger.info(f"✅ Excel file parsed: {len(df)} rows, {len(df.columns)} columns")
        
        # Handle merged cells
        if 'Product' in df.columns:
            df['Product'] = df['Product'].replace('', pd.NA).ffill().fillna('')
        if 'Feature' in df.columns:
            df['Feature'] = df['Feature'].replace('', pd.NA).ffill().fillna('N/A')
        if 'Product_Area' in df.columns:
            df['Product_Area'] = df['Product_Area'].replace('', pd.NA).ffill().fillna('')
        if 'Infrastructure' in df.columns:
            df['Infrastructure'] = df['Infrastructure'].replace('', pd.NA).ffill().fillna('')
        
        # Transform to compliance format
        records = []
        cert_mappings = get_certification_mappings()
        
        for _, row in df.iterrows():
            product = row.get('Product', '')
            if not product:
                continue
            
            # Process each certification
            cert_columns = df.columns[5:]  # After base columns
            for cert_name in cert_columns:
                cert_value = row[cert_name]
                
                # Get mapping
                mapping = cert_mappings.get(cert_name.strip(), {
                    'Region': 'Global', 'Category': '', 'Subcategory': ''
                })
                
                # Parse status and quarter
                status, quarter, notes = parse_status_and_quarter(cert_value)
                
                record = {
                    'Product': product,
                    'Feature': row.get('Feature', 'N/A'),
                    'Product Area': row.get('Product_Area', ''),
                    'Infrastructure': row.get('Infrastructure', ''),
                    'Region': mapping['Region'],
                    'Category': mapping['Category'],
                    'Subcategory': mapping['Subcategory'],
                    'Certification': cert_name.strip(),
                    'Compliance Status': status,
                    'Roadmap Quarter': quarter,
                    'Additional Information (Notes)': notes
                }
                
                records.append(record)
        
        compliance_df = pd.DataFrame(records)
        logger.info(f"✅ Generated {len(compliance_df)} compliance records")
        return compliance_df
        
    except Exception as e:
        logger.error(f"❌ Error processing Excel data: {str(e)}")
        raise


def get_certification_mappings() -> Dict[str, Dict[str, str]]:
    """Get certification mappings"""
    return {
        'SOC 2': {'Region': 'Global', 'Category': '', 'Subcategory': ''},
        'SOC 1': {'Region': 'Global', 'Category': '', 'Subcategory': ''},
        'ISO 27001': {'Region': 'Global', 'Category': '', 'Subcategory': ''},
        'ISO 27017': {'Region': 'Global', 'Category': '', 'Subcategory': ''},
        'ISO 27018': {'Region': 'Global', 'Category': '', 'Subcategory': ''},
        'ISO 9001': {'Region': 'Global', 'Category': '', 'Subcategory': ''},
        'ISO 42001': {'Region': 'Global', 'Category': '', 'Subcategory': ''},
        'PCI': {'Region': 'Global', 'Category': '', 'Subcategory': ''},
        'CSA Star - level 1': {'Region': 'Global', 'Category': '', 'Subcategory': ''},
        'CSA Star - level 2': {'Region': 'Global', 'Category': '', 'Subcategory': ''},
        'HIPAA': {'Region': 'AMER', 'Category': 'US Commercial', 'Subcategory': 'Healthcare'},
        'FedRAMP Moderate': {'Region': 'AMER', 'Category': 'USPS', 'Subcategory': 'US Government & Defense'},
        'FedRAMP High': {'Region': 'AMER', 'Category': 'USPS', 'Subcategory': 'US Government & Defense'},
        'DoD IL5': {'Region': 'AMER', 'Category': 'USPS', 'Subcategory': 'US Government & Defense'},
        'GovRAMP': {'Region': 'AMER', 'Category': 'USPS', 'Subcategory': 'SLED'},
        'TX-RAMP': {'Region': 'AMER', 'Category': 'USPS', 'Subcategory': 'SLED'},
        'NIAP / Common Criteria': {'Region': 'AMER', 'Category': 'USPS', 'Subcategory': 'On-prem'},
        'ISMAP (Japan)': {'Region': 'APJC', 'Category': '', 'Subcategory': ''},
        'IRAP (Australia)': {'Region': 'APJC', 'Category': '', 'Subcategory': ''},
        'TISAX': {'Region': 'EMEA', 'Category': '', 'Subcategory': ''},
        'Italian ACN QC1': {'Region': 'EMEA', 'Category': '', 'Subcategory': ''},
        'Italian ACN QC2': {'Region': 'EMEA', 'Category': '', 'Subcategory': ''},
        'UAE DESC': {'Region': 'EMEA', 'Category': '', 'Subcategory': ''},
        'Spain CPSTIC': {'Region': 'EMEA', 'Category': '', 'Subcategory': ''},
        'FIPS 140-2': {'Region': 'Global', 'Category': 'Technical Requirements', 'Subcategory': ''},
        'FIPS 140-3': {'Region': 'Global', 'Category': 'Technical Requirements', 'Subcategory': ''},
        'IPv6': {'Region': 'Global', 'Category': 'Technical Requirements', 'Subcategory': ''},
        'TLS 1.3': {'Region': 'Global', 'Category': 'Technical Requirements', 'Subcategory': ''},
    }


def parse_status_and_quarter(value: Any) -> tuple:
    """Parse compliance status and roadmap quarter"""
    if pd.isna(value) or value == '':
        return 'Not Applicable', '', ''
    
    value_str = str(value).strip()
    
    # Check for explicit statuses
    if value_str in ['Compliant', '✓', 'Yes']:
        return 'Compliant', '', ''
    elif value_str == 'Not Applicable':
        return 'Not Applicable', '', ''
    elif value_str in ['Not Compliant', 'Non-Compliant']:
        return 'Not Compliant', '', ''
    
    # Check for roadmap quarter patterns
    import re
    quarter_pattern = r'Q[1-4]FY\d{2}'
    match = re.search(quarter_pattern, value_str)
    
    if match:
        quarter = match.group(0)
        notes = value_str.replace(quarter, '').strip()
        return 'On Roadmap', quarter, notes
    
    return 'Not Compliant', '', value_str


def upload_to_gcs(df: pd.DataFrame, bucket_name: str) -> str:
    """Upload DataFrame to Google Cloud Storage"""
    try:
        # Create CSV content
        csv_content = df.to_csv(index=False)
        
        # Generate filename with timestamp
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        filename = f'Product_Compliance_Infra_Data_{timestamp}.csv'
        
        # Upload to GCS
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(filename)
        
        blob.upload_from_string(csv_content, content_type='text/csv')
        
        logger.info(f"✅ Uploaded to GCS: gs://{bucket_name}/{filename}")
        return filename
        
    except Exception as e:
        logger.error(f"❌ Error uploading to GCS: {str(e)}")
        raise


def send_to_splunk(df: pd.DataFrame, credentials: Dict[str, str]) -> bool:
    """Send data to Splunk HEC (optional)"""
    if not credentials.get('splunk_host') or not credentials.get('splunk_token'):
        logger.info("⚠️ Splunk credentials not configured - skipping HEC")
        return True
    
    try:
        # Prepare events
        events = []
        for _, row in df.iterrows():
            event = {
                'product': row.get('Product', ''),
                'feature': row.get('Feature', ''),
                'product_area': row.get('Product Area', ''),
                'infrastructure': row.get('Infrastructure', ''),
                'region': row.get('Region', ''),
                'category': row.get('Category', ''),
                'subcategory': row.get('Subcategory', ''),
                'certification': row.get('Certification', ''),
                'compliance_status': row.get('Compliance Status', ''),
                'roadmap_quarter': row.get('Roadmap Quarter', ''),
                'additional_information': row.get('Additional Information (Notes)', ''),
                'processing_timestamp': datetime.now(timezone.utc).isoformat(),
                'source_system': 'gcp_sharepoint_integration'
            }
            events.append(event)
        
        # Send to Splunk
        splunk_url = f"https://{credentials['splunk_host']}:8088/services/collector/event"
        headers = {
            'Authorization': f"Splunk {credentials['splunk_token']}",
            'Content-Type': 'application/json'
        }
        
        # Send in batches
        batch_size = 100
        success_count = 0
        
        for i in range(0, len(events), batch_size):
            batch = events[i:i + batch_size]
            
            splunk_event = {
                "time": int(datetime.now(timezone.utc).timestamp()),
                "index": "product_compliance",
                "source": "gcp_sharepoint_integration",
                "sourcetype": "compliance_data",
                "event": batch
            }
            
            response = requests.post(splunk_url, headers=headers, json=splunk_event, timeout=30)
            
            if response.status_code == 200:
                success_count += len(batch)
            else:
                logger.error(f"❌ Failed to send batch to Splunk: {response.status_code}")
        
        logger.info(f"✅ Sent {success_count}/{len(events)} events to Splunk")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error sending to Splunk: {str(e)}")
        return False


@functions_framework.http
def process_sharepoint_compliance(request):
    """HTTP Cloud Function for SharePoint compliance processing"""
    
    logger.info("🚀 Starting SharePoint compliance processing...")
    
    try:
        # Get credentials
        credentials = get_credentials()
        
        # Initialize SharePoint client
        client = SharePointGCPClient(credentials)
        
        # Authenticate
        if not client.authenticate():
            return {'error': 'SharePoint authentication failed'}, 500
        
        # Get site ID
        site_url = 'https://cisco.sharepoint.com/sites/Splunk-Product-Compliance'
        if not client.get_site_id(site_url):
            return {'error': 'Failed to get SharePoint site ID'}, 500
        
        # Download Excel file
        excel_content = client.download_excel('Product Compliance GTM Initiative Tracking-5.xlsx')
        if not excel_content:
            return {'error': 'Failed to download Excel file'}, 500
        
        # Process data
        compliance_df = process_excel_data(excel_content)
        
        # Upload to GCS
        filename = upload_to_gcs(compliance_df, BUCKET_NAME)
        
        # Send to Splunk (optional)
        splunk_success = send_to_splunk(compliance_df, credentials)
        
        # Prepare response
        response_data = {
            'status': 'success',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'records_processed': len(compliance_df),
            'gcs_file': f'gs://{BUCKET_NAME}/{filename}',
            'splunk_sent': splunk_success,
            'summary': {
                'total_records': len(compliance_df),
                'roadmap_items': len(compliance_df[compliance_df['Compliance Status'] == 'On Roadmap']),
                'unique_certifications': compliance_df['Certification'].nunique(),
                'unique_products': compliance_df['Product'].nunique()
            }
        }
        
        logger.info(f"✅ Processing complete: {len(compliance_df)} records processed")
        return response_data, 200
        
    except Exception as e:
        logger.error(f"❌ Processing failed: {str(e)}")
        return {'error': str(e)}, 500
