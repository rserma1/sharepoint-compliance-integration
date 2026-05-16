"""
Simple GCP Cloud Function for testing deployment
"""

import functions_framework
import json
from datetime import datetime


@functions_framework.http
def process_sharepoint_compliance_test(request):
    """Simple test function that returns success"""
    
    response_data = {
        'status': 'success',
        'message': 'SharePoint compliance processor deployed successfully!',
        'timestamp': datetime.utcnow().isoformat(),
        'mode': 'test',
        'project': 'pmops-docai-dev-e93d',
        'function': 'sharepoint-compliance-gen1'
    }
    
    return json.dumps(response_data), 200, {'Content-Type': 'application/json'}
