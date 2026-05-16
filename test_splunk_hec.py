"""
Test Splunk HEC connection and data sending
"""

import sys
import os
import json
from splunk_client import SplunkHECClient
from config import SPLUNK_CONFIG


def test_splunk_hec():
    """Test Splunk HEC connection and data sending"""
    
    print("=" * 60)
    print("Splunk HEC Connection Test")
    print("=" * 60)
    
    # Get credentials
    splunk_host = os.getenv('SPLUNK_HOST', SPLUNK_CONFIG['splunk_host'])
    hec_token = os.getenv('SPLUNK_HEC_TOKEN', SPLUNK_CONFIG['hec_token'])
    
    if not splunk_host or not hec_token:
        print("\n❌ Missing Splunk credentials!")
        print("Set environment variables:")
        print("  export SPLUNK_HOST='your-stack.splunkcloud.com'")
        print("  export SPLUNK_HEC_TOKEN='your-hec-token'")
        
        if len(sys.argv) >= 3:
            splunk_host = sys.argv[1]
            hec_token = sys.argv[2]
        else:
            sys.exit(1)
    
    print(f"\n📋 Configuration:")
    print(f"   Splunk Host: {splunk_host}")
    print(f"   Port: {SPLUNK_CONFIG['port']}")
    print(f"   Index: {SPLUNK_CONFIG['index']}")
    print(f"   Source: {SPLUNK_CONFIG['source']}")
    print(f"   Sourcetype: {SPLUNK_CONFIG['sourcetype']}")
    
    # Initialize Splunk client
    print(f"\n🔗 Initializing Splunk HEC client...")
    client = SplunkHECClient(
        splunk_host=splunk_host,
        hec_token=hec_token,
        port=SPLUNK_CONFIG['port'],
        index=SPLUNK_CONFIG['index'],
        source=SPLUNK_CONFIG['source'],
        sourcetype=SPLUNK_CONFIG['sourcetype']
    )
    
    # Test 1: Connection
    print(f"\n🔐 Test 1: HEC Connection")
    if not client.test_connection():
        print("❌ FAILED: Could not connect to Splunk HEC")
        return False
    
    print("✅ PASSED: HEC connection successful")
    
    # Test 2: Send test event
    print(f"\n📤 Test 2: Send Test Event")
    test_event = {
        'test': True,
        'message': 'HEC Test Event',
        'timestamp': '2024-01-01T00:00:00Z',
        'test_data': {
            'product': 'Test Product',
            'certification': 'Test Cert',
            'status': 'Test Status'
        }
    }
    
    if client.send_event(test_event):
        print("✅ PASSED: Test event sent successfully")
    else:
        print("❌ FAILED: Could not send test event")
        return False
    
    # Test 3: Send sample compliance data
    print(f"\n📊 Test 3: Send Sample Compliance Data")
    
    # Create sample data
    import pandas as pd
    sample_data = [
        {
            'Product': 'Test Product 1',
            'Feature': 'Test Feature 1',
            'Product Area': 'Test Area 1',
            'Infrastructure': 'Test Infra 1',
            'Region': 'Global',
            'Category': '',
            'Subcategory': '',
            'Certification': 'SOC 2',
            'Compliance Status': 'Compliant',
            'Roadmap Quarter': '',
            'Additional Information (Notes)': 'Test note 1'
        },
        {
            'Product': 'Test Product 2',
            'Feature': 'Test Feature 2',
            'Product Area': 'Test Area 2',
            'Infrastructure': 'AWS',
            'Region': 'AMER',
            'Category': 'US Commercial',
            'Subcategory': 'Healthcare',
            'Certification': 'HIPAA',
            'Compliance Status': 'On Roadmap',
            'Roadmap Quarter': 'Q3FY26',
            'Additional Information (Notes)': 'Test note 2'
        }
    ]
    
    sample_df = pd.DataFrame(sample_data)
    
    success_count, failure_count = client.send_compliance_data(sample_df)
    
    if success_count == len(sample_data):
        print(f"✅ PASSED: All {success_count} sample records sent successfully")
    else:
        print(f"⚠️  WARNING: {success_count} sent, {failure_count} failed")
    
    # Test 4: Send summary metrics
    print(f"\n📈 Test 4: Send Summary Metrics")
    if client.send_summary_metrics(sample_df):
        print("✅ PASSED: Summary metrics sent successfully")
    else:
        print("❌ FAILED: Could not send summary metrics")
        return False
    
    # Test 5: Send processing log
    print(f"\n📝 Test 5: Send Processing Log")
    if client.send_processing_log("HEC test completed successfully", "info"):
        print("✅ PASSED: Processing log sent successfully")
    else:
        print("❌ FAILED: Could not send processing log")
        return False
    
    print("\n" + "=" * 60)
    print("✅ All tests passed! Splunk HEC is working correctly.")
    print("=" * 60)
    print(f"\nYou can now run the main processor:")
    print(f"  python process_sharepoint_data.py")
    print(f"\nData will be sent to:")
    print(f"  Index: {SPLUNK_CONFIG['index']}")
    print(f"  Sourcetype: {SPLUNK_CONFIG['sourcetype']}")
    
    return True


if __name__ == '__main__':
    success = test_splunk_hec()
    sys.exit(0 if success else 1)
