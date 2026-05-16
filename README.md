# SharePoint Integration for Product Compliance

This module provides integration with SharePoint Online using Microsoft Graph API to automatically download and process the Product Compliance Excel file.

## Features

- **Automatic Download**: Downloads Excel file directly from SharePoint
- **Data Processing**: Parses and transforms compliance data (same logic as local version)
- **CSV Upload**: Optionally uploads processed CSV back to SharePoint
- **Secure Authentication**: Uses Azure AD OAuth 2.0 client credentials flow

## Prerequisites

1. **Azure AD App Registration**
   - Client ID: `6f9ebeed-1c0c-4cdb-a7cb-19718966e3bc`
   - Integration Name: `SPO_Sharepoint_Product_Compliance_PT`
   - You need the **Client Secret** and **Tenant ID**

2. **Required Permissions** (in Azure AD):
   - `Sites.Read.All` - Read SharePoint sites
   - `Files.Read.All` - Read files
   - `Files.ReadWrite.All` - Upload files (optional)

3. **Python Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Setup

1. **Install Dependencies**:
   ```bash
   cd sharepoint-integration
   pip install -r requirements.txt
   ```

2. **Configure Credentials**:
   
   **Option A: Environment Variables** (Recommended)
   ```bash
   export SHAREPOINT_CLIENT_SECRET='your-client-secret'
   export SHAREPOINT_TENANT_ID='your-tenant-id'
   ```

   **Option B: .env File**
   ```bash
   cp .env.example .env
   # Edit .env and add your credentials
   ```

   **Option C: Command Line Arguments**
   ```bash
   python process_sharepoint_data.py <client_secret> <tenant_id>
   ```

## Usage

### Basic Usage

```bash
# Set credentials
export SHAREPOINT_CLIENT_SECRET='your-secret'
export SHAREPOINT_TENANT_ID='your-tenant-id'

# Run the processor
python process_sharepoint_data.py
```

### What It Does

1. **Authenticates** with Microsoft Graph API using client credentials
2. **Connects** to SharePoint site: `https://cisco.sharepoint.com/sites/Splunk-Product-Compliance`
3. **Downloads** Excel file: `Product Compliance GTM Initiative Tracking-5.xlsx`
4. **Reads** the `Compliance Inventory` sheet
5. **Processes** data:
   - Handles merged cells
   - Parses compliance statuses
   - Extracts roadmap quarters
   - Maps certifications to regions/categories
6. **Outputs** CSV file: `Product_Compliance_Infra_Data.csv`
7. **Optionally uploads** CSV back to SharePoint

### Output

The script generates:
- `Product_Compliance_Infra_Data.csv` - Processed compliance data
- `unknown_certifications_sharepoint.json` - Any unmapped certifications (if found)

## Configuration

Edit `config.py` to customize:

```python
SHAREPOINT_CONFIG = {
    'site_url': 'https://cisco.sharepoint.com/sites/Splunk-Product-Compliance',
    'excel_file_name': 'Product Compliance GTM Initiative Tracking-5.xlsx',
    'sheet_name': 'Compliance Inventory',
    'skip_rows': 3,
    'output_csv': 'Product_Compliance_Infra_Data.csv',
}
```

## File Structure

```
sharepoint-integration/
├── README.md                      # This file
├── requirements.txt               # Python dependencies
├── .env.example                   # Example environment variables
├── config.py                      # Configuration settings
├── sharepoint_client.py           # SharePoint/Graph API client
└── process_sharepoint_data.py     # Main processing script
```

## Certification Mappings

All certifications are mapped to their respective regions:

- **Global**: SOC 2, SOC 1, ISO standards, PCI, CSA Star, FIPS, IPv6, TLS
- **AMER**: HIPAA, FedRAMP, DoD IL5, GovRAMP, TX-RAMP, NIAP
- **EMEA**: TISAX, Italian ACN QC1/QC2, UAE DESC, Spain CPSTIC
- **APJC**: ISMAP (Japan), IRAP (Australia)

## Troubleshooting

### Authentication Errors

```
❌ Authentication failed: AADSTS7000215: Invalid client secret
```
- Check your `SHAREPOINT_CLIENT_SECRET` is correct
- Verify the secret hasn't expired in Azure AD

### Site Access Errors

```
❌ Failed to get site ID: 403 Forbidden
```
- Verify the app has `Sites.Read.All` permission
- Ensure admin consent has been granted in Azure AD

### File Not Found

```
❌ Failed to download file: 404 Not Found
```
- Check the file name in `config.py` matches SharePoint
- Verify the file is in the root of the document library

## Integration with Splunk Dashboard

After processing, upload the CSV to Splunk:

```bash
# Process data from SharePoint
python process_sharepoint_data.py

# Upload to Splunk (use your Splunk upload method)
# The CSV format is identical to the local version
```

## Security Notes

- **Never commit** `.env` file or credentials to git
- Store secrets in environment variables or secure vault
- Use Azure Key Vault for production deployments
- Rotate client secrets regularly

## Support

For issues or questions:
1. Check Azure AD app permissions
2. Verify SharePoint site URL and file paths
3. Review error messages in console output
4. Check `unknown_certifications_sharepoint.json` for unmapped certifications
