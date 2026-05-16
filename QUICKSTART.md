# Quick Start Guide

## 1. Get Your Credentials

You need two pieces of information from your Azure AD administrator:

1. **Client Secret** - The secret key for app `6f9ebeed-1c0c-4cdb-a7cb-19718966e3bc`
2. **Tenant ID** - Your Cisco Azure AD tenant ID (usually a GUID)

## 2. Install Dependencies

```bash
cd sharepoint-integration
pip install -r requirements.txt
```

## 3. Set Credentials

**Option A: Environment Variables** (Recommended)
```bash
# SharePoint credentials
export SHAREPOINT_CLIENT_SECRET='your-client-secret-here'
export SHAREPOINT_TENANT_ID='your-tenant-id-here'

# Splunk HEC credentials (optional)
export SPLUNK_HOST='your-stack.splunkcloud.com'
export SPLUNK_HEC_TOKEN='your-hec-token-here'
```

**Option B: Command Line**
```bash
# SharePoint only
python process_sharepoint_data.py <client_secret> <tenant_id>
```

## 4. Run the Script

```bash
python process_sharepoint_data.py
```

## What Happens

1. ✅ Authenticates with Microsoft Graph API
2. ✅ Connects to SharePoint: `https://cisco.sharepoint.com/sites/Splunk-Product-Compliance`
3. ✅ Downloads: `Product Compliance GTM Initiative Tracking-5.xlsx`
4. ✅ Processes the `Compliance Inventory` sheet
5. ✅ Generates: `Product_Compliance_Infra_Data.csv`
6. 🔗 **Optional**: Sends data to Splunk via HEC (if configured)
7. ❓ Asks if you want to upload CSV back to SharePoint

## Output

- `Product_Compliance_Infra_Data.csv` - Ready for Splunk dashboard
- `unknown_certifications_sharepoint.json` - Any unmapped certifications (if found)

## Example Output

```
==========================================
SharePoint Product Compliance Data Processor
==========================================

📁 Connecting to SharePoint...
   Site: https://cisco.sharepoint.com/sites/Splunk-Product-Compliance
   File: Product Compliance GTM Initiative Tracking-5.xlsx

✅ Authentication successful
✅ Site ID retrieved: cisco.sharepoint.com,abc123...
✅ File downloaded: Product Compliance GTM Initiative Tracking-5.xlsx (245678 bytes)
✅ Excel file parsed: 268 rows, 33 columns

🔄 Processing merged cells...
🔄 Transforming data to compliance format...
Generated 7728 compliance records

✅ Success! Output saved to: Product_Compliance_Infra_Data.csv
Total records: 7728
```

## Troubleshooting

### "Authentication failed"
- Check your client secret is correct
- Verify the secret hasn't expired

### "Failed to get site ID"
- Verify app has `Sites.Read.All` permission
- Check admin consent was granted

### "Failed to download file"
- Verify file name matches: `Product Compliance GTM Initiative Tracking-5.xlsx`
- Check file is in the root of the document library

## Splunk HEC Setup (Optional)

To send data directly to Splunk:

### 1. Create HEC Token in Splunk
1. Go to Splunk Cloud → Settings → Data Inputs → HTTP Event Collector
2. Click "New Token"
3. Configure:
   - Name: `product_compliance_sharepoint`
   - Index: `product_compliance` (or your preferred index)
   - Source Type: `compliance_data`
   - Enable SSL: Yes
4. Copy the generated HEC Token

### 2. Test HEC Connection
```bash
python test_splunk_hec.py <splunk_host> <hec_token>
```

### 3. Run with Splunk Integration
```bash
export SPLUNK_HOST='your-stack.splunkcloud.com'
export SPLUNK_HEC_TOKEN='your-hec-token'
python process_sharepoint_data.py
```

## Next Steps

- **Option 1**: Upload CSV to Splunk manually
- **Option 2**: Use HEC integration for automatic data ingestion
