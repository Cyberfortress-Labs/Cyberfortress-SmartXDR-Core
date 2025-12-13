"""
IRIS API Service - Integration với DFIR-IRIS Case Management
"""
import os
import re
import json
import logging
import requests
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# Setup logger
logger = logging.getLogger('smartxdr.iris')

load_dotenv()


class IRISService:
    """
    Service để tương tác với IRIS API
    """
    
    def __init__(self):
        self.iris_url = os.getenv("IRIS_API_URL")
        self.api_key = os.getenv("IRIS_API_KEY")
        
        # SSL verification settings
        self.verify_ssl = os.getenv("IRIS_VERIFY_SSL", "false").lower() == "true"
        self.ca_cert = os.getenv("IRIS_CA_CERT", None)
        
        if not self.api_key:
            raise ValueError("IRIS_API_KEY not found in environment variables")
    
    def get_ioc_intelowl_report(self, case_id, ioc_id):
        """
        Lấy IntelOwl report từ IOC attributes
        
        Returns:
            {
                "html_report": "...",          # HTML rendered
                "raw_data": {...},             # Raw JSON (nếu có)
                "external_link": "...",
                "playbook_name": "..."
            }
        """
        # 1. Get IOC details
        verify = self.ca_cert if self.ca_cert else self.verify_ssl
        
        response = requests.get(
            f"{self.iris_url}/case/ioc/{ioc_id}",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type":  "application/json"
            },
            params={"cid": case_id},
            verify=verify
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to get IOC: {response.text}")
        
        ioc_data = response.json()['data']
        
        # 2. Parse custom_attributes
        custom_attrs = ioc_data.get('custom_attributes', {})
        
        # Debug: print structure
        logger.debug(f"IOC custom_attributes type: {type(custom_attrs)}")
        
        # IntelOwl data nằm trong tab "IntelOwl Report"
        intelowl_tab = None
        
        # Handle different structures
        if isinstance(custom_attrs, dict):
            # custom_attributes is a dict, check if IntelOwl Report exists
            for key, value in custom_attrs.items():
                logger.debug(f" Checking key: {key}")
                if 'IntelOwl' in str(key) or 'intelowl' in str(key).lower():
                    intelowl_tab = value
                    logger.debug(f" Found IntelOwl data in key: {key}")
                    break
        elif isinstance(custom_attrs, list):
            # custom_attributes is a list of objects
            for attr in custom_attrs:
                if isinstance(attr, dict) and attr.get('tab_name') == 'IntelOwl Report':
                    intelowl_tab = attr
                    logger.debug(f" Found IntelOwl tab in list")
                    break
        
        if not intelowl_tab:
            logger.debug(f" No IntelOwl Report found in custom_attributes")
            return None
        
        # DEBUG: Chi tiết IntelOwl tab
        logger.debug(f" IntelOwl tab type: {type(intelowl_tab)}")
        
        # Extract HTML report - handle different structures
        html_report = ""
        if isinstance(intelowl_tab, str):
            # Direct HTML string
            html_report = intelowl_tab
            logger.debug(f" IntelOwl tab is string, length: {len(html_report)}")
        elif isinstance(intelowl_tab, dict):
            logger.debug(f" IntelOwl tab keys: {list(intelowl_tab.keys())}")
            
            # Check for nested structure: {'HTML report': {'value': '...'}}
            if 'HTML report' in intelowl_tab:
                html_report_obj = intelowl_tab['HTML report']
                if isinstance(html_report_obj, dict) and 'value' in html_report_obj:
                    html_report = html_report_obj['value']
                    logger.debug(f" Extracted from nested 'HTML report'.'value', length: {len(html_report)}")
                else:
                    html_report = str(html_report_obj)
            # Try different possible keys
            elif 'value' in intelowl_tab:
                html_report = str(intelowl_tab['value'])
            elif 'content' in intelowl_tab:
                html_report = str(intelowl_tab['content'])
            elif 'html' in intelowl_tab:
                html_report = str(intelowl_tab['html'])
            else:
                # Convert entire dict to string as last resort
                html_report = str(intelowl_tab)
            
            logger.debug(f" Final HTML length: {len(html_report)}")
        
        logger.debug(f" HTML report preview (first 500 chars): {html_report[:500]}")
        
        # Extract raw data từ HTML (nếu có embed)
        raw_data = self._extract_raw_json_from_html(html_report)
        
        return {
            "ioc_value": ioc_data['ioc_value'],
            "ioc_type": ioc_data['ioc_type']['type_name'],
            "html_report": html_report,
            "raw_data": raw_data
        }

    def _extract_raw_json_from_html(self, html_report):
        """
        Extract raw JSON từ HTML report
        HTML chứa: <div id='intelowl_raw_ace'>{... JSON ...}</div>
        """
        # Tìm JSON trong div intelowl_raw_ace
        match = re.search(r"<div id='intelowl_raw_ace'>(.*?)</div>", html_report, re.DOTALL)
        
        if match:
            json_str = match.group(1).strip()
            try:
                return json.loads(json_str)
            except Exception as e:
                logger.debug(f" Failed to parse JSON: {e}")
                logger.debug(f" JSON string preview: {json_str[:200]}")
                pass
        else:
            logger.debug(f" No 'intelowl_raw_ace' div found in HTML")
        
        return None
    def get_case_iocs(self, case_id: int) -> list:
        """
        Lấy tất cả IOCs từ một case
        
        Args:
            case_id: Case ID
        
        Returns:
            List of IOC objects with ioc_id, ioc_value, ioc_type
        """
        verify = self.ca_cert if self.ca_cert else self.verify_ssl
        
        response = requests.get(
            f"{self.iris_url}/case/ioc/list",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            params={"cid": case_id},
            verify=verify
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to get case IOCs: {response.text}")
        
        data = response.json()
        
        # Debug: print response structure
        logger.debug(f"get_case_iocs] Response data type: {type(data)}")
        logger.debug(f"get_case_iocs] Response data: {str(data)[:500]}")
        
        # Handle IRIS API response
        if isinstance(data, dict) and 'data' in data:
            ioc_data = data['data']
            logger.debug(f"get_case_iocs] ioc_data type: {type(ioc_data)}")
            if isinstance(ioc_data, dict) and 'ioc' in ioc_data:
                ioc_list = ioc_data['ioc']
            elif isinstance(ioc_data, list):
                ioc_list = ioc_data
            else:
                ioc_list = []
        else:
            ioc_list = []
        
        logger.debug(f"get_case_iocs] ioc_list type: {type(ioc_list)}, len: {len(ioc_list) if isinstance(ioc_list, list) else 'N/A'}")
        if ioc_list and len(ioc_list) > 0:
            logger.debug(f"get_case_iocs] First IOC type: {type(ioc_list[0])}")
            logger.debug(f"get_case_iocs] First IOC: {ioc_list[0]}")
        
        # Extract relevant fields
        result = []
        for ioc in ioc_list:
            # Skip if ioc is not a dict (could be string key from dict iteration)
            if not isinstance(ioc, dict):
                logger.debug(f"get_case_iocs] Skipping non-dict IOC: {ioc}")
                continue
                
            # Handle ioc_type as string or dict
            ioc_type_raw = ioc.get('ioc_type', 'unknown')
            if isinstance(ioc_type_raw, dict):
                ioc_type = ioc_type_raw.get('type_name', 'unknown')
            else:
                ioc_type = str(ioc_type_raw) if ioc_type_raw else 'unknown'
            
            result.append({
                "ioc_id": ioc.get('ioc_id'),
                "ioc_value": ioc.get('ioc_value'),
                "ioc_type": ioc_type,
                "ioc_description": ioc.get('ioc_description', '')
            })
        
        return result
        
    def add_ioc_comment(self, case_id: int, ioc_id: int, comment: str) -> Dict[str, Any]:
        """
        Thêm comment vào IOC trên IRIS
        
        Args:
            case_id: Case ID
            ioc_id: IOC ID
            comment: Nội dung comment
        
        Returns:
            Response từ IRIS API
        """
        verify = self.ca_cert if self.ca_cert else self.verify_ssl
        
        response = requests.post(
            f"{self.iris_url}/case/ioc/{ioc_id}/comments/add",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            params={"cid": case_id},
            json={
                "comment_text": comment
            },
            verify=verify
        )
        
        if response.status_code not in [200, 201]:
            raise Exception(f"Failed to add comment: {response.text}")
        
        return response.json()
    
    def get_ioc_comments(self, case_id: int, ioc_id: int) -> list:
        """
        Lấy danh sách comments của một IOC
        
        Args:
            case_id: Case ID
            ioc_id: IOC ID
        
        Returns:
            List of comments
        """
        verify = self.ca_cert if self.ca_cert else self.verify_ssl
        
        response = requests.get(
            f"{self.iris_url}/case/ioc/{ioc_id}/comments/list",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            params={"cid": case_id},
            verify=verify
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to get IOC comments: {response.text}")
        
        data = response.json()
        
        # Handle IRIS API response structure
        if isinstance(data, dict) and 'data' in data:
            return data['data'] if isinstance(data['data'], list) else []
        
        return []
    
    def get_case_ioc_smartxdr_comments(self, case_id: int) -> Dict[str, Any]:
        """
        Lấy comment mới nhất của SmartXDR cho mỗi IOC trong case
        
        Args:
            case_id: Case ID
        
        Returns:
            {
                "case_id": 52,
                "total_iocs": 4,
                "iocs_with_analysis": 4,
                "iocs": [
                    {
                        "ioc_id": 147,
                        "ioc_value": "/root/eicar.com",
                        "ioc_type": "filename",
                        "smartxdr_comment": {
                            "comment_id": 123,
                            "comment_text": "...",
                            "comment_date": "2025-12-01T..."
                        }
                    },
                    ...
                ]
            }
        """
        # 1. Get all IOCs from case
        iocs = self.get_case_iocs(case_id)
        
        result = {
            "case_id": case_id,
            "total_iocs": len(iocs),
            "iocs_with_analysis": 0,
            "iocs": []
        }
        
        # 2. For each IOC, get comments and find SmartXDR's latest
        for ioc in iocs:
            ioc_id = ioc['ioc_id']
            ioc_entry = {
                "ioc_id": ioc_id,
                "ioc_value": ioc['ioc_value'],
                "ioc_type": ioc['ioc_type'],
                "smartxdr_comment": None
            }
            
            try:
                comments = self.get_ioc_comments(case_id, ioc_id)
                
                # Find SmartXDR comments (contains "[SmartXDR AI Analysis]")
                smartxdr_comments = [
                    c for c in comments
                    if '[SmartXDR AI Analysis]' in c.get('comment_text', '')
                ]
                
                if smartxdr_comments:
                    # Sort by date descending and get the latest
                    smartxdr_comments.sort(
                        key=lambda x: x.get('comment_date', ''),
                        reverse=True
                    )
                    latest = smartxdr_comments[0]
                    
                    ioc_entry['smartxdr_comment'] = {
                        "comment_id": latest.get('comment_id'),
                        "comment_text": latest.get('comment_text', ''),
                        "comment_date": latest.get('comment_date'),
                        "comment_user": latest.get('comment_user', {}).get('user_name', 'SmartXDR')
                    }
                    result['iocs_with_analysis'] += 1
                    
            except Exception as e:
                logger.warning(f" Failed to get comments for IOC {ioc_id}: {e}")
            
            result['iocs'].append(ioc_entry)
        
        return result