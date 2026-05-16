"""
Process Product Compliance data from SharePoint
"""

import sys
import os
import pandas as pd
import json
from typing import List, Dict, Any
from sharepoint_client import SharePointClient
from splunk_client import SplunkHECClient, create_splunk_client_from_config
from config import SHAREPOINT_CONFIG, CERT_MAPPINGS, SPLUNK_CONFIG


def read_excel_with_merged_cells(df: pd.DataFrame) -> pd.DataFrame:
    """Handle merged cells by forward-filling."""
    if 'Product' in df.columns:
        df['Product'] = df['Product'].replace('', pd.NA).ffill().fillna('')
    if 'Feature' in df.columns:
        df['Feature'] = df['Feature'].replace('', pd.NA).ffill().fillna('N/A')
    if 'Product_Area' in df.columns:
        df['Product_Area'] = df['Product_Area'].replace('', pd.NA).ffill().fillna('')
    if 'Infrastructure' in df.columns:
        df['Infrastructure'] = df['Infrastructure'].replace('', pd.NA).ffill().fillna('')
    
    return df


def parse_status_and_quarter(value: Any) -> tuple:
    """
    Parse compliance status and roadmap quarter from cell value.
    
    Returns:
        tuple: (status, quarter, notes)
    """
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
    
    # Check for roadmap quarter patterns (Q#FY##)
    import re
    quarter_pattern = r'Q[1-4]FY\d{2}'
    match = re.search(quarter_pattern, value_str)
    
    if match:
        quarter = match.group(0)
        # Check if there's additional text (notes)
        notes = value_str.replace(quarter, '').strip()
        return 'On Roadmap', quarter, notes
    
    # Default to Not Compliant for any other value
    return 'Not Compliant', '', value_str


def transform_to_compliance_format(df: pd.DataFrame) -> pd.DataFrame:
    """Transform wide format Excel to long format compliance data."""
    
    # Find certification columns (after base columns)
    base_col_names = ['Product', 'Feature', 'Product_Area', 'Infrastructure']
    cert_start_idx = 5  # After 'In production?' column
    
    cert_columns = df.columns[cert_start_idx:]
    print(f"Found {len(cert_columns)} certification columns: {list(cert_columns)[:5]}...")
    
    # Track unknown certifications
    unknown_certs = set()
    unknown_data = {}
    
    records = []
    
    for idx, row in df.iterrows():
        product = row.get('Product', '')
        if pd.isna(product):
            product = row.iloc[1] if len(row) > 1 else ''
        
        feature_raw = row.get('Feature', row.iloc[2] if len(row) > 2 else 'N/A')
        feature = 'N/A' if pd.isna(feature_raw) else feature_raw
        
        product_area = row.get('Product_Area', '')
        if pd.isna(product_area):
            product_area = row.iloc[3] if len(row) > 3 else ''
        
        infrastructure = row.get('Infrastructure', '')
        if pd.isna(infrastructure):
            infrastructure = row.iloc[4] if len(row) > 4 else ''
        
        # Skip rows without product
        if not product or product == '':
            continue
        
        # Process each certification
        for cert_name in cert_columns:
            cert_value = row[cert_name]
            
            # Normalize certification name (handle trailing spaces)
            cert_name_normalized = cert_name.strip()
            
            # Get mapping or mark as unknown
            if cert_name_normalized in CERT_MAPPINGS:
                mapping = CERT_MAPPINGS[cert_name_normalized]
            elif cert_name in CERT_MAPPINGS:
                mapping = CERT_MAPPINGS[cert_name]
            else:
                unknown_certs.add(cert_name)
                if cert_name not in unknown_data:
                    unknown_data[cert_name] = {
                        'Region': 'Global',
                        'Category': '',
                        'Subcategory': '',
                        'Note': 'Please update with correct region/category'
                    }
                mapping = unknown_data[cert_name]
            
            # Parse status and quarter
            status, quarter, notes = parse_status_and_quarter(cert_value)
            
            record = {
                'Product': product,
                'Feature': feature,
                'Product Area': product_area,
                'Infrastructure': infrastructure,
                'Region': mapping['Region'],
                'Category': mapping['Category'],
                'Subcategory': mapping['Subcategory'],
                'Certification': cert_name_normalized if cert_name_normalized in CERT_MAPPINGS else cert_name,
                'Compliance Status': status,
                'Roadmap Quarter': quarter,
                'Additional Information (Notes)': notes
            }
            
            records.append(record)
    
    # Save unknown certifications
    if unknown_certs:
        unknown_file = 'unknown_certifications_sharepoint.json'
        with open(unknown_file, 'w') as f:
            json.dump(unknown_data, f, indent=2)
        print(f"\nFound {len(unknown_certs)} unknown certifications. Saved to {unknown_file} for review.")
        print(f"Unknown certifications: {', '.join(sorted(unknown_certs))}")
    
    return pd.DataFrame(records)


def main():
    """Main function to process SharePoint data"""
    
    print("=" * 60)
    print("SharePoint Product Compliance Data Processor")
    print("=" * 60)
    
    # Get SharePoint credentials from environment variables or command line
    client_id = os.getenv('SHAREPOINT_CLIENT_ID', SHAREPOINT_CONFIG['client_id'])
    client_secret = os.getenv('SHAREPOINT_CLIENT_SECRET')
    tenant_id = os.getenv('SHAREPOINT_TENANT_ID')
    
    # Get Splunk credentials
    splunk_host = os.getenv('SPLUNK_HOST', SPLUNK_CONFIG['splunk_host'])
    hec_token = os.getenv('SPLUNK_HEC_TOKEN', SPLUNK_CONFIG['hec_token'])
    
    if not client_secret or not tenant_id:
        print("\n❌ Missing SharePoint credentials!")
        print("Please set environment variables:")
        print("  export SHAREPOINT_CLIENT_SECRET='your-client-secret'")
        print("  export SHAREPOINT_TENANT_ID='your-tenant-id'")
        print("\nOr provide them as command line arguments:")
        print(f"  python {sys.argv[0]} <client_secret> <tenant_id>")
        
        if len(sys.argv) >= 3:
            client_secret = sys.argv[1]
            tenant_id = sys.argv[2]
        else:
            sys.exit(1)
    
    # Initialize Splunk client (optional)
    splunk_client = None
    if splunk_host and hec_token:
        print(f"\n🔗 Initializing Splunk connection...")
        splunk_client = SplunkHECClient(
            splunk_host=splunk_host,
            hec_token=hec_token,
            port=SPLUNK_CONFIG['port'],
            index=SPLUNK_CONFIG['index'],
            source=SPLUNK_CONFIG['source'],
            sourcetype=SPLUNK_CONFIG['sourcetype']
        )
        
        # Test Splunk connection
        if splunk_client.test_connection():
            print("✅ Splunk HEC connection successful")
        else:
            print("⚠️  Splunk HEC connection failed - data will not be sent to Splunk")
            splunk_client = None
    else:
        print("\n⚠️  Splunk credentials not provided - data will not be sent to Splunk")
        print("Set environment variables to enable Splunk integration:")
        print("  export SPLUNK_HOST='your-stack.splunkcloud.com'")
        print("  export SPLUNK_HEC_TOKEN='your-hec-token'")
    
    # Initialize SharePoint client
    print(f"\n📁 Connecting to SharePoint...")
    print(f"   Site: {SHAREPOINT_CONFIG['site_url']}")
    print(f"   File: {SHAREPOINT_CONFIG['excel_file_name']}")
    
    client = SharePointClient(client_id, client_secret, tenant_id)
    
    # Authenticate
    if not client.authenticate():
        print("❌ Authentication failed. Exiting.")
        sys.exit(1)
    
    # Get site ID
    if not client.get_site_id(SHAREPOINT_CONFIG['site_url']):
        print("❌ Failed to get site ID. Exiting.")
        sys.exit(1)
    
    # Download and read Excel file
    print(f"\n📥 Downloading Excel file from SharePoint...")
    df = client.read_excel_from_sharepoint(
        SHAREPOINT_CONFIG['excel_file_name'],
        SHAREPOINT_CONFIG['sheet_name'],
        SHAREPOINT_CONFIG['skip_rows']
    )
    
    if df is None:
        print("❌ Failed to read Excel file. Exiting.")
        sys.exit(1)
    
    print(f"Read {len(df)} rows from Excel")
    print(f"Columns: {list(df.columns)[:10]}...")
    
    # Handle merged cells
    print("\n🔄 Processing merged cells...")
    df = read_excel_with_merged_cells(df)
    
    # Transform data
    print("\n🔄 Transforming data to compliance format...")
    compliance_df = transform_to_compliance_format(df)
    
    print(f"Generated {len(compliance_df)} compliance records")
    
    # Save to CSV
    output_file = SHAREPOINT_CONFIG['output_csv']
    compliance_df.to_csv(output_file, index=False)
    print(f"\n✅ Success! Output saved to: {output_file}")
    print(f"Total records: {len(compliance_df)}")
    
    # Show sample
    print("\nFirst few records:")
    print(compliance_df.head(10).to_string())
    
    # Send data to Splunk if configured
    if splunk_client:
        print(f"\n📤 Sending data to Splunk...")
        splunk_client.send_processing_log("Starting data transmission to Splunk", "info")
        
        # Send compliance data
        success_count, failure_count = splunk_client.send_compliance_data(compliance_df)
        
        # Send summary metrics
        if splunk_client.send_summary_metrics(compliance_df):
            print("✅ Summary metrics sent to Splunk")
        
        # Log completion
        splunk_client.send_processing_log(
            f"Data transmission complete: {success_count} sent, {failure_count} failed", 
            "info"
        )
        
        print(f"✅ Splunk transmission complete: {success_count} events sent")
    else:
        print(f"\n⚠️  Data not sent to Splunk (HEC not configured)")
    
    # Optional: Upload CSV back to SharePoint
    upload_choice = input("\n📤 Upload CSV to SharePoint? (y/n): ").strip().lower()
    if upload_choice == 'y':
        if client.upload_file(output_file):
            print(f"✅ CSV uploaded to SharePoint: {output_file}")
        else:
            print("❌ Failed to upload CSV to SharePoint")


if __name__ == '__main__':
    main()
