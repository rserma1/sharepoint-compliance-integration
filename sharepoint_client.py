"""
SharePoint Client for Microsoft Graph API Integration
"""

import requests
import msal
import io
import pandas as pd
from typing import Optional, Dict, Any
from config import SHAREPOINT_CONFIG, GRAPH_API_CONFIG


class SharePointClient:
    """Client for interacting with SharePoint via Microsoft Graph API"""
    
    def __init__(self, client_id: str, client_secret: str, tenant_id: str):
        """
        Initialize SharePoint client
        
        Args:
            client_id: Azure AD application client ID
            client_secret: Azure AD application client secret
            tenant_id: Azure AD tenant ID
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self.access_token = None
        self.site_id = None
        
    def authenticate(self) -> bool:
        """
        Authenticate with Microsoft Graph API using client credentials flow
        
        Returns:
            bool: True if authentication successful
        """
        try:
            authority = f"https://login.microsoftonline.com/{self.tenant_id}"
            app = msal.ConfidentialClientApplication(
                self.client_id,
                authority=authority,
                client_credential=self.client_secret,
            )
            
            result = app.acquire_token_for_client(scopes=GRAPH_API_CONFIG['scopes'])
            
            if "access_token" in result:
                self.access_token = result['access_token']
                print("✅ Authentication successful")
                return True
            else:
                print(f"❌ Authentication failed: {result.get('error_description', 'Unknown error')}")
                return False
                
        except Exception as e:
            print(f"❌ Authentication error: {str(e)}")
            return False
    
    def get_site_id(self, site_url: str) -> Optional[str]:
        """
        Get SharePoint site ID from site URL
        
        Args:
            site_url: SharePoint site URL
            
        Returns:
            str: Site ID or None if failed
        """
        try:
            # Extract hostname and site path from URL
            from urllib.parse import urlparse
            parsed = urlparse(site_url)
            hostname = parsed.netloc
            site_path = parsed.path
            
            # Get site ID using Graph API
            endpoint = f"{GRAPH_API_CONFIG['graph_endpoint']}/sites/{hostname}:{site_path}"
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Accept': 'application/json'
            }
            
            response = requests.get(endpoint, headers=headers)
            
            if response.status_code == 200:
                site_data = response.json()
                self.site_id = site_data['id']
                print(f"✅ Site ID retrieved: {self.site_id}")
                return self.site_id
            else:
                print(f"❌ Failed to get site ID: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Error getting site ID: {str(e)}")
            return None
    
    def get_file_content(self, file_name: str) -> Optional[bytes]:
        """
        Download file content from SharePoint
        
        Args:
            file_name: Name of the file to download
            
        Returns:
            bytes: File content or None if failed
        """
        try:
            if not self.site_id:
                print("❌ Site ID not set. Call get_site_id() first.")
                return None
            
            # Search for the file
            endpoint = f"{GRAPH_API_CONFIG['graph_endpoint']}/sites/{self.site_id}/drive/root:/{file_name}:/content"
            headers = {
                'Authorization': f'Bearer {self.access_token}',
            }
            
            response = requests.get(endpoint, headers=headers)
            
            if response.status_code == 200:
                print(f"✅ File downloaded: {file_name} ({len(response.content)} bytes)")
                return response.content
            else:
                print(f"❌ Failed to download file: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Error downloading file: {str(e)}")
            return None
    
    def read_excel_from_sharepoint(self, file_name: str, sheet_name: str, skip_rows: int = 0) -> Optional[pd.DataFrame]:
        """
        Read Excel file from SharePoint and return as DataFrame
        
        Args:
            file_name: Name of the Excel file
            sheet_name: Name of the sheet to read
            skip_rows: Number of rows to skip
            
        Returns:
            pd.DataFrame: DataFrame or None if failed
        """
        try:
            file_content = self.get_file_content(file_name)
            
            if file_content:
                # Read Excel from bytes
                excel_file = io.BytesIO(file_content)
                df = pd.read_excel(
                    excel_file, 
                    sheet_name=sheet_name, 
                    skiprows=skip_rows,
                    keep_default_na=False,
                    na_values=['']
                )
                print(f"✅ Excel file parsed: {len(df)} rows, {len(df.columns)} columns")
                return df
            else:
                return None
                
        except Exception as e:
            print(f"❌ Error reading Excel file: {str(e)}")
            return None
    
    def upload_file(self, file_path: str, destination_name: Optional[str] = None) -> bool:
        """
        Upload file to SharePoint
        
        Args:
            file_path: Local path to file
            destination_name: Name for file in SharePoint (defaults to original name)
            
        Returns:
            bool: True if upload successful
        """
        try:
            if not self.site_id:
                print("❌ Site ID not set. Call get_site_id() first.")
                return False
            
            import os
            if not destination_name:
                destination_name = os.path.basename(file_path)
            
            # Read file content
            with open(file_path, 'rb') as f:
                file_content = f.read()
            
            # Upload file
            endpoint = f"{GRAPH_API_CONFIG['graph_endpoint']}/sites/{self.site_id}/drive/root:/{destination_name}:/content"
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/octet-stream'
            }
            
            response = requests.put(endpoint, headers=headers, data=file_content)
            
            if response.status_code in [200, 201]:
                print(f"✅ File uploaded: {destination_name}")
                return True
            else:
                print(f"❌ Failed to upload file: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Error uploading file: {str(e)}")
            return False
