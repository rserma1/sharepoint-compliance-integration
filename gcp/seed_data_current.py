"""
Seed Data Generator using Current Excel Dataset
Uses the actual Product_Compliance_Infra_Data.csv as seed data
"""

import pandas as pd
import json
from datetime import datetime, timezone
from typing import Dict, Any
import os


def load_current_dataset() -> pd.DataFrame:
    """Load the current dataset from the CSV file"""
    try:
        # Try to load from the current directory first
        csv_path = '../Product_Compliance_Infra_Data.csv'
        if not os.path.exists(csv_path):
            # Try alternative paths
            csv_path = '../../Product_Compliance_Infra_Data.csv'
        
        if not os.path.exists(csv_path):
            raise FileNotFoundError("Product_Compliance_Infra_Data.csv not found")
        
        df = pd.read_csv(csv_path)
        print(f"✅ Loaded current dataset: {len(df)} records")
        return df
        
    except Exception as e:
        print(f"❌ Error loading current dataset: {str(e)}")
        # Fallback to generated data
        return generate_fallback_data()


def generate_fallback_data() -> pd.DataFrame:
    """Generate fallback data if CSV is not available"""
    print("⚠️ Using fallback generated data")
    
    # Sample data similar to the real dataset
    products = [
        "Splunk Enterprise", "Splunk Cloud Platform", "Splunk AI Assistant",
        "Splunk Attack Analyzer", "SOAR", "Admin Config Service",
        "Real User Monitoring", "Dashboard AI Assistant"
    ]
    
    features = ["N/A", "Ingest Monitoring", "AI Features", "Security Analytics"]
    product_areas = ["Platform", "Security", "Analytics", "IT Operations"]
    infrastructures = ["AWS", "Azure", "GCP", "On-Premise / CMP"]
    
    certifications = [
        "SOC 2", "SOC 1", "ISO 27001", "ISO 27017", "ISO 27018", "ISO 9001",
        "ISO 42001", "PCI", "CSA Star - level 1", "CSA Star - level 2",
        "HIPAA", "FedRAMP Moderate", "FedRAMP High", "DoD IL5", "GovRAMP",
        "TX-RAMP", "NIAP / Common Criteria", "ISMAP (Japan)", "IRAP (Australia)",
        "TISAX", "Italian ACN QC1", "Italian ACN QC2", "UAE DESC",
        "Spain CPSTIC", "FIPS 140-2", "FIPS 140-3", "IPv6", "TLS 1.3"
    ]
    
    compliance_statuses = ["Compliant", "On Roadmap", "Not Compliant", "Not Applicable"]
    roadmap_quarters = ["Q3FY26", "Q4FY26", "Q1FY27", "Q2FY27", "Q3FY27"]
    
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
    
    import random
    records = []
    
    for i in range(100):  # Generate 100 fallback records
        product = random.choice(products)
        feature = random.choice(features)
        product_area = random.choice(product_areas)
        infrastructure = random.choice(infrastructures)
        certification = random.choice(certifications)
        
        mapping = cert_mappings.get(certification, {
            'Region': 'Global', 'Category': '', 'Subcategory': ''
        })
        
        status_weights = {
            'Compliant': 0.4,
            'On Roadmap': 0.2,
            'Not Compliant': 0.2,
            'Not Applicable': 0.2
        }
        status = random.choices(compliance_statuses, weights=list(status_weights.values()))[0]
        
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


def create_seed_data_file() -> str:
    """Create a seed data file from the current dataset"""
    
    # Load current dataset
    df = load_current_dataset()
    
    # Save as seed data file
    seed_filename = 'seed_compliance_data.json'
    
    # Convert to JSON format for easy loading
    seed_data = {
        'metadata': {
            'source': 'Product_Compliance_Infra_Data.csv',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'total_records': len(df),
            'unique_products': df['Product'].nunique(),
            'unique_certifications': df['Certification'].nunique(),
            'status_distribution': df['Compliance Status'].value_counts().to_dict(),
            'region_distribution': df['Region'].value_counts().to_dict()
        },
        'data': df.to_dict('records')
    }
    
    # Save seed data
    with open(seed_filename, 'w') as f:
        json.dump(seed_data, f, indent=2)
    
    print(f"✅ Seed data file created: {seed_filename}")
    print(f"   Records: {len(df)}")
    print(f"   Products: {df['Product'].nunique()}")
    print(f"   Certifications: {df['Certification'].nunique()}")
    
    return seed_filename


def load_seed_data() -> pd.DataFrame:
    """Load seed data from file"""
    try:
        with open('seed_compliance_data.json', 'r') as f:
            seed_data = json.load(f)
        
        df = pd.DataFrame(seed_data['data'])
        print(f"✅ Loaded seed data: {len(df)} records")
        return df
        
    except FileNotFoundError:
        print("⚠️ Seed data file not found, creating from current dataset")
        create_seed_data_file()
        return load_seed_data()
    except Exception as e:
        print(f"❌ Error loading seed data: {str(e)}")
        return generate_fallback_data()


def get_dataset_summary() -> Dict[str, Any]:
    """Get summary of the current dataset"""
    df = load_current_dataset()
    
    return {
        'total_records': len(df),
        'unique_products': df['Product'].nunique(),
        'unique_certifications': df['Certification'].nunique(),
        'unique_infrastructures': df['Infrastructure'].nunique(),
        'status_distribution': df['Compliance Status'].value_counts().to_dict(),
        'region_distribution': df['Region'].value_counts().to_dict(),
        'roadmap_items': len(df[df['Compliance Status'] == 'On Roadmap']),
        'sample_products': df['Product'].unique()[:5].tolist(),
        'sample_certifications': df['Certification'].unique()[:10].tolist()
    }


if __name__ == '__main__':
    # Create seed data file
    seed_file = create_seed_data_file()
    
    # Show summary
    summary = get_dataset_summary()
    print("\n📊 Dataset Summary:")
    print(f"   Total Records: {summary['total_records']}")
    print(f"   Products: {summary['unique_products']}")
    print(f"   Certifications: {summary['unique_certifications']}")
    print(f"   Roadmap Items: {summary['roadmap_items']}")
    print(f"   Status Distribution: {summary['status_distribution']}")
    print(f"   Region Distribution: {summary['region_distribution']}")
