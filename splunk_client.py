"""
Splunk HTTP Event Collector (HEC) Client
"""

import requests
import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SplunkHECClient:
    """Client for sending data to Splunk via HTTP Event Collector"""
    
    def __init__(self, splunk_host: str, hec_token: str, port: int = 8088, 
                 index: str = 'main', source: str = 'sharepoint_integration', 
                 sourcetype: str = 'json'):
        """
        Initialize Splunk HEC Client
        
        Args:
            splunk_host: Splunk Cloud hostname (e.g., 'splunkcloud.com')
            hec_token: HEC token from Splunk
            port: HEC port (default 8088)
            index: Splunk index to send data to
            source: Source name for events
            sourcetype: Sourcetype for events
        """
        self.splunk_host = splunk_host
        self.hec_token = hec_token
        self.port = port
        self.index = index
        self.source = source
        self.sourcetype = sourcetype
        self.hec_url = f"https://{splunk_host}:{port}/services/collector/event"
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Splunk {hec_token}',
            'Content-Type': 'application/json'
        })
    
    def test_connection(self) -> bool:
        """Test connection to Splunk HEC"""
        try:
            test_event = {
                "time": int(time.time()),
                "index": self.index,
                "source": self.source,
                "sourcetype": self.sourcetype,
                "event": {
                    "message": "HEC Connection Test",
                    "test": True,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }
            
            response = self.session.post(self.hec_url, json=test_event, timeout=30)
            
            if response.status_code == 200:
                logger.info("✅ HEC connection test successful")
                return True
            else:
                logger.error(f"❌ HEC connection failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ HEC connection error: {str(e)}")
            return False
    
    def send_event(self, event_data: Dict[str, Any], 
                   index: Optional[str] = None, 
                   source: Optional[str] = None,
                   sourcetype: Optional[str] = None) -> bool:
        """
        Send a single event to Splunk
        
        Args:
            event_data: Event data dictionary
            index: Override default index
            source: Override default source
            sourcetype: Override default sourcetype
            
        Returns:
            bool: True if successful
        """
        try:
            splunk_event = {
                "time": int(time.time()),
                "index": index or self.index,
                "source": source or self.source,
                "sourcetype": sourcetype or self.sourcetype,
                "event": event_data
            }
            
            response = self.session.post(self.hec_url, json=splunk_event, timeout=30)
            
            if response.status_code == 200:
                logger.debug(f"✅ Event sent successfully")
                return True
            else:
                logger.error(f"❌ Failed to send event: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error sending event: {str(e)}")
            return False
    
    def send_compliance_data(self, compliance_df, batch_size: int = 100) -> tuple:
        """
        Send compliance data to Splunk
        
        Args:
            compliance_df: Pandas DataFrame with compliance data
            batch_size: Number of events to send per batch
            
        Returns:
            tuple: (success_count, failure_count)
        """
        logger.info(f"📤 Sending {len(compliance_df)} compliance records to Splunk...")
        
        success_count = 0
        failure_count = 0
        
        # Convert DataFrame to list of events
        events = []
        for _, row in compliance_df.iterrows():
            event = {
                'product': row.get('Product', ''),
                'feature': row.get('Feature', ''),
                'product_area': row.get('Product Area', ''),
                'infrastructure': row.get('Infrastructure', ''),
                'region': row.get('Region', ''),
                'category': row.get('Category', ''),
                'subcategory': row.get('Subcategory', ''),
                'certification': row.get('Certification', ''),
                'compliance_status': row.get('Compliance Status', ''),
                'roadmap_quarter': row.get('Roadmap Quarter', ''),
                'additional_information': row.get('Additional Information (Notes)', ''),
                'processing_timestamp': datetime.now(timezone.utc).isoformat(),
                'source_system': 'sharepoint_integration'
            }
            events.append(event)
        
        # Send events in batches
        for i in range(0, len(events), batch_size):
            batch = events[i:i + batch_size]
            batch_success = 0
            
            for event in batch:
                if self.send_event(event):
                    batch_success += 1
                else:
                    failure_count += 1
            
            success_count += batch_success
            logger.info(f"📊 Batch {i//batch_size + 1}: {batch_success}/{len(batch)} events sent")
            
            # Small delay between batches to avoid overwhelming Splunk
            if i + batch_size < len(events):
                time.sleep(0.1)
        
        logger.info(f"✅ Summary: {success_count} sent, {failure_count} failed")
        return success_count, failure_count
    
    def send_summary_metrics(self, compliance_df) -> bool:
        """Send summary metrics to Splunk"""
        try:
            # Calculate summary metrics
            total_records = len(compliance_df)
            status_counts = compliance_df['Compliance Status'].value_counts().to_dict()
            region_counts = compliance_df['Region'].value_counts().to_dict()
            roadmap_items = len(compliance_df[compliance_df['Compliance Status'] == 'On Roadmap'])
            
            # Create summary event
            summary_event = {
                'event_type': 'compliance_summary',
                'processing_timestamp': datetime.now(timezone.utc).isoformat(),
                'metrics': {
                    'total_records': total_records,
                    'roadmap_items': roadmap_items,
                    'status_distribution': status_counts,
                    'region_distribution': region_counts,
                    'unique_certifications': compliance_df['Certification'].nunique(),
                    'unique_products': compliance_df['Product'].nunique()
                }
            }
            
            return self.send_event(summary_event, sourcetype='compliance_summary')
            
        except Exception as e:
            logger.error(f"❌ Error sending summary: {str(e)}")
            return False
    
    def send_processing_log(self, message: str, level: str = 'info') -> bool:
        """Send a processing log message to Splunk"""
        log_event = {
            'event_type': 'processing_log',
            'level': level,
            'message': message,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'source_system': 'sharepoint_integration'
        }
        
        return self.send_event(log_event, sourcetype='processing_log')


def create_splunk_client_from_config(config: Dict[str, Any]) -> SplunkHECClient:
    """Create Splunk client from configuration dictionary"""
    return SplunkHECClient(
        splunk_host=config['splunk_host'],
        hec_token=config['hec_token'],
        port=config.get('port', 8088),
        index=config.get('index', 'main'),
        source=config.get('source', 'sharepoint_integration'),
        sourcetype=config.get('sourcetype', 'json')
    )
