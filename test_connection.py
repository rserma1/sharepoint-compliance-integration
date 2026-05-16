"""
Test SharePoint connection and credentials
"""

import sys
import os
from sharepoint_client import SharePointClient
from config import SHAREPOINT_CONFIG

def test_connection():
    """Test SharePoint connection"""
    
    print("=" * 60)
    print("SharePoint Connection Test")
    print("=" * 60)
    
    # Get credentials
    client_id = os.getenv('SHAREPOINT_CLIENT_ID', SHAREPOINT_CONFIG['client_id'])
    client_secret = os.getenv('SHAREPOINT_CLIENT_SECRET')
    tenant_id = os.getenv('SHAREPOINT_TENANT_ID')
    
    if not client_secret or not tenant_id:
        print("\n❌ Missing credentials!")
        print("Set environment variables:")
        print("  export SHAREPOINT_CLIENT_SECRET='your-secret'")
        print("  export SHAREPOINT_TENANT_ID='your-tenant-id'")
        
        if len(sys.argv) >= 3:
            client_secret = sys.argv[1]
            tenant_id = sys.argv[2]
        else:
            sys.exit(1)
    
    print(f"\n📋 Configuration:")
    print(f"   Client ID: {client_id}")
    print(f"   Tenant ID: {tenant_id[:8]}...")
    print(f"   Site URL: {SHAREPOINT_CONFIG['site_url']}")
    
    # Test 1: Authentication
    print(f"\n🔐 Test 1: Authentication")
    client = SharePointClient(client_id, client_secret, tenant_id)
    
    if not client.authenticate():
        print("❌ FAILED: Could not authenticate")
        return False
    
    print("✅ PASSED: Authentication successful")
    
    # Test 2: Get Site ID
    print(f"\n🌐 Test 2: Get Site ID")
    site_id = client.get_site_id(SHAREPOINT_CONFIG['site_url'])
    
    if not site_id:
        print("❌ FAILED: Could not get site ID")
        return False
    
    print(f"✅ PASSED: Site ID retrieved")
    
    # Test 3: List files (optional)
    print(f"\n📁 Test 3: Check file access")
    print(f"   Looking for: {SHAREPOINT_CONFIG['excel_file_name']}")
    
    # Try to get file metadata (not download full file)
    try:
        import requests
        endpoint = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root:/{SHAREPOINT_CONFIG['excel_file_name']}"
        headers = {'Authorization': f'Bearer {client.access_token}'}
        response = requests.get(endpoint, headers=headers)
        
        if response.status_code == 200:
            file_info = response.json()
            print(f"✅ PASSED: File found")
            print(f"   Name: {file_info.get('name')}")
            print(f"   Size: {file_info.get('size')} bytes")
            print(f"   Modified: {file_info.get('lastModifiedDateTime')}")
        else:
            print(f"⚠️  WARNING: File not accessible (status {response.status_code})")
            print(f"   This might be normal if file is in a subfolder")
    except Exception as e:
        print(f"⚠️  WARNING: Could not check file: {str(e)}")
    
    print("\n" + "=" * 60)
    print("✅ All tests passed! Ready to process data.")
    print("=" * 60)
    print("\nRun: python process_sharepoint_data.py")
    
    return True


if __name__ == '__main__':
    success = test_connection()
    sys.exit(0 if success else 1)
