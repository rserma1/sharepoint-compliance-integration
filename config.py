"""
SharePoint Configuration for Product Compliance Integration
"""

# SharePoint Configuration
SHAREPOINT_CONFIG = {
    'site_url': 'https://cisco.sharepoint.com/sites/Splunk-Product-Compliance',
    'integration_name': 'SPO_Sharepoint_Product_Compliance_PT',
    'client_id': '6f9ebeed-1c0c-4cdb-a7cb-19718966e3bc',
    
    # File paths in SharePoint
    'excel_file_name': 'Product Compliance GTM Initiative Tracking-5.xlsx',
    'sheet_name': 'Compliance Inventory',
    'skip_rows': 3,
    
    # Output configuration
    'output_csv': 'Product_Compliance_Infra_Data.csv',
}

# Graph API Configuration
GRAPH_API_CONFIG = {
    'authority': 'https://login.microsoftonline.com/common',
    'scopes': ['https://graph.microsoft.com/.default'],
    'graph_endpoint': 'https://graph.microsoft.com/v1.0',
}

# Splunk HEC Configuration
SPLUNK_CONFIG = {
    'splunk_host': '',  # e.g., 'your-stack.splunkcloud.com'
    'hec_token': '',    # HEC token from Splunk
    'port': 8088,
    'index': 'product_compliance',  # Your Splunk index
    'source': 'sharepoint_integration',
    'sourcetype': 'compliance_data'
}

# Certification Mappings (same as convert_infra_sheet.py)
CERT_MAPPINGS = {
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
