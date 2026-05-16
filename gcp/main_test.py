"""
GCP Cloud Function for SharePoint Compliance Data Processing - Test Version
Uses seed data for testing without real SharePoint credentials
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
from typing import Dict, List, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
PROJECT_ID = os.environ.get('GCP_PROJECT')
BUCKET_NAME = os.environ.get('GCS_BUCKET', f'product-compliance-data-{PROJECT_ID}')
SECRET_PREFIX = os.environ.get('SECRET_PREFIX', 'sharepoint-compliance')
USE_SEED_DATA = os.environ.get('USE_SEED_DATA', 'true').lower() == 'true'


def access_secret_version(project_id: str, secret_id: str, version_id: str = "latest") -> str:
    """Access secret version from Secret Manager"""
    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        logger.warning(f"Could not access secret {secret_id}: {str(e)}")
        return None


def get_test_credentials() -> Dict[str, str]:
    """Get test credentials (mock values)"""
    return {
        'client_id': '6f9ebeed-1c0c-4cdb-a7cb-19718966e3bc',
        'client_secret': 'test-client-secret-for-testing',
        'tenant_id': 'test-tenant-id-for-testing',
        'splunk_host': 'test-stack.splunkcloud.com',
        'splunk_token': 'test-hec-token-for-testing'
    }


def load_current_dataset() -> pd.DataFrame:
    """Load the current dataset from the embedded seed data"""
    try:
        # Current dataset summary based on the actual Product_Compliance_Infra_Data.csv
        current_data = [
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "Global", "Category": "", "Subcategory": "", "Certification": "SOC 2", "Compliance Status": "Compliant", "Roadmap Quarter": "", "Additional Information (Notes)": ""},
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "Global", "Category": "", "Subcategory": "", "Certification": "SOC 1", "Compliance Status": "Compliant", "Roadmap Quarter": "", "Additional Information (Notes)": ""},
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "Global", "Category": "", "Subcategory": "", "Certification": "ISO 27001", "Compliance Status": "Compliant", "Roadmap Quarter": "", "Additional Information (Notes)": ""},
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "Global", "Category": "", "Subcategory": "", "Certification": "ISO 27017", "Compliance Status": "Compliant", "Roadmap Quarter": "", "Additional Information (Notes)": ""},
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "Global", "Category": "", "Subcategory": "", "Certification": "ISO 27018", "Compliance Status": "Compliant", "Roadmap Quarter": "", "Additional Information (Notes)": ""},
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "Global", "Category": "", "Subcategory": "", "Certification": "ISO 9001", "Compliance Status": "Compliant", "Roadmap Quarter": "", "Additional Information (Notes)": ""},
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "Global", "Category": "", "Subcategory": "", "Certification": "ISO 42001", "Compliance Status": "Not Applicable", "Roadmap Quarter": "", "Additional Information (Notes)": ""},
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "Global", "Category": "", "Subcategory": "", "Certification": "PCI", "Compliance Status": "Compliant", "Roadmap Quarter": "", "Additional Information (Notes)": ""},
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "Global", "Category": "", "Subcategory": "", "Certification": "CSA Star - level 1", "Compliance Status": "Compliant", "Roadmap Quarter": "", "Additional Information (Notes)": ""},
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "Global", "Category": "", "Subcategory": "", "Certification": "CSA Star - level 2", "Compliance Status": "Compliant", "Roadmap Quarter": "", "Additional Information (Notes)": ""},
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "AMER", "Category": "US Commercial", "Subcategory": "Healthcare", "Certification": "HIPAA", "Compliance Status": "Compliant", "Roadmap Quarter": "", "Additional Information (Notes)": ""},
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "AMER", "Category": "USPS", "Subcategory": "US Government & Defense", "Certification": "FedRAMP Moderate", "Compliance Status": "Compliant", "Roadmap Quarter": "", "Additional Information (Notes)": ""},
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "AMER", "Category": "USPS", "Subcategory": "US Government & Defense", "Certification": "FedRAMP High", "Compliance Status": "Compliant", "Roadmap Quarter": "", "Additional Information (Notes)": ""},
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "AMER", "Category": "USPS", "Subcategory": "US Government & Defense", "Certification": "DoD IL5", "Compliance Status": "Compliant", "Roadmap Quarter": "", "Additional Information (Notes)": ""},
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "AMER", "Category": "USPS", "Subcategory": "SLED", "Certification": "GovRAMP", "Compliance Status": "Compliant", "Roadmap Quarter": "", "Additional Information (Notes)": ""},
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "AMER", "Category": "USPS", "Subcategory": "SLED", "Certification": "TX-RAMP", "Compliance Status": "Compliant", "Roadmap Quarter": "", "Additional Information (Notes)": ""},
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "AMER", "Category": "USPS", "Subcategory": "On-prem", "Certification": "NIAP / Common Criteria", "Compliance Status": "Not Applicable", "Roadmap Quarter": "", "Additional Information (Notes)": ""},
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "APJC", "Category": "", "Subcategory": "", "Certification": "ISMAP (Japan)", "Compliance Status": "Compliant", "Roadmap Quarter": "", "Additional Information (Notes)": ""},
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "APJC", "Category": "", "Subcategory": "", "Certification": "IRAP (Australia)", "Compliance Status": "Compliant", "Roadmap Quarter": "", "Additional Information (Notes)": ""},
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "EMEA", "Category": "", "Subcategory": "", "Certification": "TISAX", "Compliance Status": "Compliant", "Roadmap Quarter": "", "Additional Information (Notes)": ""},
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "EMEA", "Category": "", "Subcategory": "", "Certification": "Italian ACN QC1", "Compliance Status": "Compliant", "Roadmap Quarter": "", "Additional Information (Notes)": ""},
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "EMEA", "Category": "", "Subcategory": "", "Certification": "Italian ACN QC2", "Compliance Status": "On Roadmap", "Roadmap Quarter": "Q3FY26", "Additional Information (Notes)": ""},
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "EMEA", "Category": "", "Subcategory": "", "Certification": "UAE DESC", "Compliance Status": "Compliant", "Roadmap Quarter": "", "Additional Information (Notes)": ""},
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "EMEA", "Category": "", "Subcategory": "", "Certification": "Spain CPSTIC", "Compliance Status": "Compliant", "Roadmap Quarter": "", "Additional Information (Notes)": ""},
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "Global", "Category": "Technical Requirements", "Subcategory": "", "Certification": "FIPS 140-2", "Compliance Status": "Compliant", "Roadmap Quarter": "", "Additional Information (Notes)": ""},
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "Global", "Category": "Technical Requirements", "Subcategory": "", "Certification": "FIPS 140-3", "Compliance Status": "Compliant", "Roadmap Quarter": "", "Additional Information (Notes)": ""},
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "Global", "Category": "Technical Requirements", "Subcategory": "", "Certification": "IPv6", "Compliance Status": "Compliant", "Roadmap Quarter": "", "Additional Information (Notes)": ""},
            {"Product": "Splunk Enterprise", "Feature": "N/A", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "Global", "Category": "Technical Requirements", "Subcategory": "", "Certification": "TLS 1.3", "Compliance Status": "Compliant", "Roadmap Quarter": "", "Additional Information (Notes)": ""},
            # Add some roadmap items for variety
            {"Product": "Splunk Cloud Platform", "Feature": "Ingest Monitoring", "Product Area": "Platform", "Infrastructure": "AWS", "Region": "Global", "Category": "", "Subcategory": "", "Certification": "ISO 42001", "Compliance Status": "On Roadmap", "Roadmap Quarter": "Q3FY27", "Additional Information (Notes)": "Target completion: Q3FY27"},
            {"Product": "Splunk AI Assistant", "Feature": "AI Features", "Product Area": "Analytics", "Infrastructure": "Azure", "Region": "Global", "Category": "", "Subcategory": "", "Certification": "ISO 27001", "Compliance Status": "On Roadmap", "Roadmap Quarter": "Q4FY26", "Additional Information (Notes)": "Target completion: Q4FY26"},
            {"Product": "SOAR", "Feature": "Automation", "Product Area": "Security", "Infrastructure": "GCP", "Region": "Global", "Category": "", "Subcategory": "", "Certification": "FedRAMP Moderate", "Compliance Status": "On Roadmap", "Roadmap Quarter": "Q1FY27", "Additional Information (Notes)": "Target completion: Q1FY27"},
        ]
        
        # Add more records to reach a good sample size
        additional_products = ["Splunk Cloud Platform", "Splunk AI Assistant", "SOAR", "Admin Config Service", "Real User Monitoring"]
        additional_infra = ["Azure", "GCP", "On-Premise / CMP", "Hybrid"]
        
        for i in range(50):  # Add 50 more records
            product = random.choice(additional_products)
            infra = random.choice(additional_infra)
            
            # Use a subset of certifications for additional records
            cert = random.choice(["SOC 2", "ISO 27001", "HIPAA", "FedRAMP Moderate", "PCI"])
            
            # Determine status and region based on certification
            if cert == "HIPAA":
                region = "AMER"
                category = "US Commercial"
                subcategory = "Healthcare"
            elif "FedRAMP" in cert:
                region = "AMER"
                category = "USPS"
                subcategory = "US Government & Defense"
            else:
                region = "Global"
                category = ""
                subcategory = ""
            
            # Random status
            status = random.choice(["Compliant", "On Roadmap", "Not Compliant", "Not Applicable"])
            quarter = random.choice(["Q3FY26", "Q4FY26", "Q1FY27", "Q2FY27"]) if status == "On Roadmap" else ""
            notes = f"Target completion: {quarter}" if status == "On Roadmap" else ""
            
            current_data.append({
                "Product": product,
                "Feature": random.choice(["N/A", "Core Features", "Advanced Features"]),
                "Product Area": random.choice(["Platform", "Security", "Analytics"]),
                "Infrastructure": infra,
                "Region": region,
                "Category": category,
                "Subcategory": subcategory,
                "Certification": cert,
                "Compliance Status": status,
                "Roadmap Quarter": quarter,
                "Additional Information (Notes)": notes
            })
        
        df = pd.DataFrame(current_data)
        print(f"✅ Loaded current dataset: {len(df)} records")
        return df
        
    except Exception as e:
        print(f"❌ Error loading current dataset: {str(e)}")
        # Fallback to generated data
        return generate_fallback_data()


def generate_fallback_data() -> pd.DataFrame:
    """Generate fallback data if current dataset fails"""
    print("⚠️ Using fallback generated data")
    
    import random
    
    # Sample data similar to the real dataset
    products = ["Splunk Enterprise", "Splunk Cloud Platform", "Splunk AI Assistant"]
    features = ["N/A", "Ingest Monitoring", "AI Features"]
    product_areas = ["Platform", "Security", "Analytics"]
    infrastructures = ["AWS", "Azure", "GCP"]
    
    certifications = ["SOC 2", "ISO 27001", "HIPAA", "FedRAMP Moderate", "PCI"]
    compliance_statuses = ["Compliant", "On Roadmap", "Not Compliant", "Not Applicable"]
    roadmap_quarters = ["Q3FY26", "Q4FY26", "Q1FY27"]
    
    records = []
    
    for i in range(30):  # Smaller fallback dataset
        product = random.choice(products)
        feature = random.choice(features)
        product_area = random.choice(product_areas)
        infrastructure = random.choice(infrastructures)
        certification = random.choice(certifications)
        
        # Determine region based on certification
        if certification == "HIPAA":
            region = "AMER"
            category = "US Commercial"
            subcategory = "Healthcare"
        elif "FedRAMP" in certification:
            region = "AMER"
            category = "USPS"
            subcategory = "US Government & Defense"
        else:
            region = "Global"
            category = ""
            subcategory = ""
        
        status = random.choice(compliance_statuses)
        quarter = random.choice(roadmap_quarters) if status == "On Roadmap" else ""
        notes = f"Target completion: {quarter}" if status == "On Roadmap" else ""
        
        record = {
            'Product': product,
            'Feature': feature,
            'Product Area': product_area,
            'Infrastructure': infrastructure,
            'Region': region,
            'Category': category,
            'Subcategory': subcategory,
            'Certification': certification,
            'Compliance Status': status,
            'Roadmap Quarter': quarter,
            'Additional Information (Notes)': notes
        }
        
        records.append(record)
    
    return pd.DataFrame(records)


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
    """Send data to Splunk HEC (mock for testing)"""
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
                'source_system': 'gcp_sharepoint_integration_test'
            }
            events.append(event)
        
        # Mock Splunk HEC call (don't actually send in test mode)
        logger.info(f"📤 Mock Splunk HEC: Would send {len(events)} events to {credentials['splunk_host']}")
        
        # In test mode, we'll just log the first few events
        logger.info(f"📊 Sample events: {json.dumps(events[:2], indent=2)}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error sending to Splunk: {str(e)}")
        return False


@functions_framework.http
def process_sharepoint_compliance_test(request):
    """HTTP Cloud Function for SharePoint compliance processing - Test Version"""
    
    logger.info("🚀 Starting SharePoint compliance processing (TEST MODE)...")
    
    try:
        # Determine if we should use seed data
        if USE_SEED_DATA:
            logger.info("📊 Using current dataset for testing")
            compliance_df = load_current_dataset()
            logger.info(f"✅ Loaded {len(compliance_df)} test records")
        else:
            logger.info("🔗 Attempting real SharePoint connection...")
            # Here we would normally connect to SharePoint
            # For now, fall back to current dataset
            compliance_df = load_current_dataset()
            logger.info(f"✅ Loaded {len(compliance_df)} fallback records")
        
        # Upload to GCS
        filename = upload_to_gcs(compliance_df, BUCKET_NAME)
        
        # Send to Splunk (mock in test mode)
        test_credentials = get_test_credentials()
        splunk_success = send_to_splunk(compliance_df, test_credentials)
        
        # Prepare response
        response_data = {
            'status': 'success',
            'mode': 'test',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'records_processed': len(compliance_df),
            'gcs_file': f'gs://{BUCKET_NAME}/{filename}',
            'splunk_sent': splunk_success,
            'use_seed_data': USE_SEED_DATA,
            'summary': {
                'total_records': len(compliance_df),
                'roadmap_items': len(compliance_df[compliance_df['Compliance Status'] == 'On Roadmap']),
                'unique_certifications': compliance_df['Certification'].nunique(),
                'unique_products': compliance_df['Product'].nunique(),
                'status_distribution': compliance_df['Compliance Status'].value_counts().to_dict(),
                'region_distribution': compliance_df['Region'].value_counts().to_dict()
            },
            'sample_data': compliance_df.head(3).to_dict('records')
        }
        
        logger.info(f"✅ Test processing complete: {len(compliance_df)} records processed")
        return response_data, 200
        
    except Exception as e:
        logger.error(f"❌ Test processing failed: {str(e)}")
        return {'error': str(e), 'mode': 'test'}, 500


@functions_framework.http
def generate_seed_data_endpoint(request):
    """Endpoint to generate seed data on demand"""
    
    try:
        # Get number of records from request
        request_json = request.get_json(silent=True) or {}
        num_records = request_json.get('num_records', 50)
        
        logger.info(f"📊 Generating {num_records} seed records...")
        
        # Generate seed data
        df = generate_seed_compliance_data(num_records)
        
        # Upload to GCS
        filename = upload_to_gcs(df, BUCKET_NAME)
        
        response_data = {
            'status': 'success',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'records_generated': len(df),
            'gcs_file': f'gs://{BUCKET_NAME}/{filename}',
            'summary': {
                'total_records': len(df),
                'roadmap_items': len(df[df['Compliance Status'] == 'On Roadmap']),
                'unique_certifications': df['Certification'].nunique(),
                'unique_products': df['Product'].nunique(),
                'status_distribution': df['Compliance Status'].value_counts().to_dict()
            },
            'sample_data': df.head(5).to_dict('records')
        }
        
        logger.info(f"✅ Seed data generated: {len(df)} records")
        return response_data, 200
        
    except Exception as e:
        logger.error(f"❌ Seed data generation failed: {str(e)}")
        return {'error': str(e)}, 500
