"""
Seed Data Generator for Testing SharePoint Integration
Generates mock compliance data for testing without real SharePoint access
"""

import pandas as pd
import json
from datetime import datetime, timezone
from typing import List, Dict, Any
import random


def generate_seed_compliance_data(num_records: int = 100) -> pd.DataFrame:
    """Generate mock compliance data for testing"""
    
    # Sample data
    products = [
        "Splunk Cloud Platform", "Splunk Enterprise", "Splunk AI Assistant",
        "Splunk Attack Analyzer", "SOAR", "Admin Config Service",
        "Real User Monitoring", "Dashboard AI Assistant", "Enterprise Security",
        "Detection Studio", "IT Service Intelligence", "User Behavior Analytics"
    ]
    
    features = [
        "N/A", "Ingest Monitoring", "AI Features", "Security Analytics",
        "Automation", "Configuration Management", "Performance Monitoring",
        "Dashboard Features", "Threat Detection", "Service Monitoring"
    ]
    
    product_areas = ["Platform", "Security", "Analytics", "IT Operations", "AI/ML"]
    infrastructures = ["AWS", "Azure", "GCP", "On-Premise / CMP", "Hybrid"]
    
    certifications = [
        "SOC 2", "SOC 1", "ISO 27001", "ISO 27017", "ISO 27018", "ISO 9001",
        "ISO 42001", "PCI", "CSA Star - level 1", "CSA Star - level 2",
        "HIPAA", "FedRAMP Moderate", "FedRAMP High", "DoD IL5", "GovRAMP",
        "TX-RAMP", "NIAP / Common Criteria", "ISMAP (Japan)", "IRAP (Australia)",
        "TISAX", "Italian ACN QC1", "Italian ACN QC2", "UAE DESC",
        "Spain CPSTIC", "FIPS 140-2", "FIPS 140-3", "IPv6", "TLS 1.3"
    ]
    
    compliance_statuses = ["Compliant", "On Roadmap", "Not Compliant", "Not Applicable"]
    roadmap_quarters = ["Q3FY26", "Q4FY26", "Q1FY27", "Q2FY27", "Q3FY27", "Q4FY27"]
    
    # Certification mappings
    cert_mappings = {
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
    
    records = []
    
    for i in range(num_records):
        product = random.choice(products)
        feature = random.choice(features)
        product_area = random.choice(product_areas)
        infrastructure = random.choice(infrastructures)
        certification = random.choice(certifications)
        
        # Get mapping for this certification
        mapping = cert_mappings.get(certification, {
            'Region': 'Global', 'Category': '', 'Subcategory': ''
        })
        
        # Weighted status distribution
        status_weights = {
            'Compliant': 0.4,
            'On Roadmap': 0.2,
            'Not Compliant': 0.2,
            'Not Applicable': 0.2
        }
        status = random.choices(compliance_statuses, weights=list(status_weights.values()))[0]
        
        # If On Roadmap, assign a quarter
        quarter = ""
        notes = ""
        if status == "On Roadmap":
            quarter = random.choice(roadmap_quarters)
            notes = f"Target completion: {quarter}"
        elif status == "Not Applicable":
            notes = "Not applicable for this product/infrastructure"
        elif status == "Not Compliant":
            notes = "Remediation in progress"
        
        record = {
            'Product': product,
            'Feature': feature,
            'Product Area': product_area,
            'Infrastructure': infrastructure,
            'Region': mapping['Region'],
            'Category': mapping['Category'],
            'Subcategory': mapping['Subcategory'],
            'Certification': certification,
            'Compliance Status': status,
            'Roadmap Quarter': quarter,
            'Additional Information (Notes)': notes
        }
        
        records.append(record)
    
    return pd.DataFrame(records)


def create_seed_excel_file(filename: str = "seed_compliance_data.xlsx"):
    """Create a seed Excel file that mimics the SharePoint format"""
    
    # Generate seed data
    df = generate_seed_compliance_data(200)
    
    # Create wide format (similar to SharePoint Excel)
    base_cols = ['Product', 'Feature', 'Product Area', 'Infrastructure']
    cert_cols = [
        'SOC 2', 'SOC 1', 'ISO 27001', 'ISO 27017', 'ISO 27018', 'ISO 9001',
        'ISO 42001', 'PCI', 'CSA Star - level 1', 'CSA Star - level 2',
        'HIPAA', 'FedRAMP Moderate', 'FedRAMP High', 'DoD IL5', 'GovRAMP',
        'TX-RAMP', 'NIAP / Common Criteria', 'ISMAP (Japan)', 'IRAP (Australia)',
        'TISAX', 'Italian ACN QC1', 'Italian ACN QC2', 'UAE DESC',
        'Spain CPSTIC', 'FIPS 140-2', 'FIPS 140-3', 'IPv6', 'TLS 1.3'
    ]
    
    # Create wide format DataFrame
    wide_data = []
    for product in df['Product'].unique():
        product_data = df[df['Product'] == product].iloc[0]
        
        row = {
            'In production?': '✓',
            'Product': product,
            'Feature': product_data['Feature'],
            'Product_Area': product_data['Product Area'],
            'Infrastructure': product_data['Infrastructure']
        }
        
        # Add certification columns
        for cert in cert_cols:
            cert_data = df[(df['Product'] == product) & (df['Certification'] == cert)]
            if len(cert_data) > 0:
                status = cert_data.iloc[0]['Compliance Status']
                quarter = cert_data.iloc[0]['Roadmap Quarter']
                
                if status == 'Compliant':
                    row[cert] = '✓'
                elif status == 'On Roadmap':
                    row[cert] = quarter
                elif status == 'Not Applicable':
                    row[cert] = 'Not Applicable'
                else:
                    row[cert] = 'Not Compliant'
            else:
                row[cert] = 'Not Applicable'
        
        wide_data.append(row)
    
    wide_df = pd.DataFrame(wide_data)
    
    # Save to Excel
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        # Create the Compliance Inventory sheet
        wide_df.to_excel(writer, sheet_name='Compliance Inventory', index=False)
        
        # Add a header row with spacing (to mimic skiprows=3)
        workbook = writer.book
        worksheet = writer.sheets['Compliance Inventory']
        
        # Insert 3 empty rows at the beginning
        worksheet.insert_rows(1, 3)
        
        # Add title in row 1
        worksheet['A1'] = 'Product Compliance GTM Initiative Tracking'
        worksheet['A2'] = 'Seed Data for Testing'
        worksheet['A3'] = f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
    
    print(f"✅ Seed Excel file created: {filename}")
    print(f"   Records: {len(wide_df)} products")
    print(f"   Certifications: {len(cert_cols)}")
    
    return filename


def create_mock_sharepoint_response() -> Dict[str, Any]:
    """Create a mock SharePoint API response"""
    
    # Generate seed data
    df = generate_seed_compliance_data(50)
    
    return {
        'status': 'success',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'records_processed': len(df),
        'gcs_file': f'gs://product-compliance-data-pmops-docai-dev-e93d/Product_Compliance_Infra_Data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
        'splunk_sent': True,
        'summary': {
            'total_records': len(df),
            'roadmap_items': len(df[df['Compliance Status'] == 'On Roadmap']),
            'unique_certifications': df['Certification'].nunique(),
            'unique_products': df['Product'].nunique(),
            'status_distribution': df['Compliance Status'].value_counts().to_dict(),
            'region_distribution': df['Region'].value_counts().to_dict()
        },
        'sample_data': df.head(5).to_dict('records')
    }


if __name__ == '__main__':
    # Create seed Excel file
    excel_file = create_seed_excel_file()
    
    # Create mock response
    mock_response = create_mock_sharepoint_response()
    
    # Save mock response for testing
    with open('mock_response.json', 'w') as f:
        json.dump(mock_response, f, indent=2)
    
    print(f"✅ Mock response saved: mock_response.json")
    print("\n📊 Generated Data Summary:")
    print(f"   Products: {mock_response['summary']['unique_products']}")
    print(f"   Certifications: {mock_response['summary']['unique_certifications']}")
    print(f"   Roadmap Items: {mock_response['summary']['roadmap_items']}")
    print(f"   Status Distribution: {mock_response['summary']['status_distribution']}")
