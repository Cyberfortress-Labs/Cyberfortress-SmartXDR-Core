from app.utils.logger import enrich_logger as logger
"""
IOC Enrichment Service - Orchestrates IOC analysis and description updates

This service coordinates:
1. Getting IntelOwl reports from IRIS IOCs
2. Generating AI analysis via LLMService
3. Adding comments to IOCs
4. Updating IOC descriptions with summaries
"""
from typing import Optional, Dict, Any

class EnrichService:
    """
    Service để enrich IOC với AI analysis
    """
    
    def __init__(self):
        self._iris_service = None
        self._llm_service = None
    
    @property
    def iris_service(self):
        """Lazy load IRISService"""
        if self._iris_service is None:
            from app.services.iris_service import IRISService
            self._iris_service = IRISService()
        return self._iris_service
    
    @property
    def llm_service(self):
        """Lazy load LLMService"""
        if self._llm_service is None:
            from app.services.llm_service import LLMService
            self._llm_service = LLMService()
        return self._llm_service
    
    def enrich_ioc_with_analysis(
        self, 
        case_id: int, 
        ioc_id: int,
        update_description: bool = True
    ) -> Dict[str, Any]:
        """
        Enrich một IOC với AI analysis và cập nhật description
        
        Flow:
        1. Get IntelOwl report từ IOC
        2. Generate AI analysis
        3. Add comment với analysis
        4. Summarize và update IOC description (nếu update_description=True)
        
        Args:
            case_id: IRIS Case ID
            ioc_id: IOC ID
            update_description: Whether to update IOC description after adding comment
        
        Returns:
            Dict with status, comment, and description update result
        """
        result = {
            "status": "success",
            "ioc_id": ioc_id,
            "case_id": case_id,
            "comment_added": False,
            "description_updated": False,
            "analysis": None,
            "summary": None
        }
        
        try:
            # 1. Get IntelOwl report from IOC
            logger.info(f"Getting IntelOwl report for IOC {ioc_id} in case {case_id}")
            report = self.iris_service.get_ioc_intelowl_report(case_id, ioc_id)
            
            if not report:
                result["status"] = "no_report"
                result["message"] = "No IntelOwl report found for this IOC"
                return result
            
            # 2. Generate AI analysis using LLMService
            logger.info(f"Generating AI analysis for {report['ioc_value']}")
            analysis_result = self.llm_service.explain_intelowl_result(
                ioc_value=report['ioc_value'],
                ioc_type=report['ioc_type'],
                raw_data=report.get('raw_data'),
                html_report=report.get('html_report')
            )
            
            if analysis_result.get("status") != "success":
                result["status"] = "analysis_failed"
                result["error"] = analysis_result.get("error", "Unknown error")
                return result
            
            analysis_text = analysis_result.get("explanation", "")
            result["analysis"] = analysis_text
            
            # 3. Add comment to IOC
            comment_text = f"[SmartXDR AI Analysis]\n\n{analysis_text}"
            logger.info(f"Adding comment to IOC {ioc_id}")
            
            self.iris_service.add_ioc_comment(case_id, ioc_id, comment_text)
            result["comment_added"] = True
            
            # 4. Update IOC description (if enabled)
            if update_description:
                result = self._update_ioc_description(
                    case_id, ioc_id, comment_text, result
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to enrich IOC {ioc_id}: {e}", exc_info=True)
            result["status"] = "error"
            result["error"] = str(e)
            return result
    
    def _update_ioc_description(
        self, 
        case_id: int, 
        ioc_id: int, 
        comment_text: str,
        result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update IOC description với summary của comment
        
        - Nếu IOC chưa có description → add new
        - Nếu IOC đã có description → append (không ghi đè)
        """
        try:
            # Get current IOC description
            ioc_data = self.iris_service.get_ioc(case_id, ioc_id)
            current_desc = ioc_data.get('ioc_description', '') or ''
            
            # Summarize the comment
            summary = self.llm_service.summarize_for_ioc_description(comment_text)
            result["summary"] = summary
            
            if not summary:
                logger.warning(f"Empty summary for IOC {ioc_id}")
                return result
            
            # Build new description (append, not overwrite)
            timestamp = self._get_timestamp()
            smartxdr_summary = f"[SmartXDR {timestamp}] {summary}"
            
            if current_desc.strip():
                # Append to existing description
                new_desc = f"{current_desc}\n\n{smartxdr_summary}"
            else:
                # No existing description, add new
                new_desc = smartxdr_summary
            
            # Update IOC
            logger.info(f"Updating description for IOC {ioc_id}")
            self.iris_service.update_ioc(
                case_id=case_id,
                ioc_id=ioc_id,
                description=new_desc
            )
            result["description_updated"] = True
            result["new_description"] = new_desc
            
        except Exception as e:
            logger.error(f"Failed to update IOC description: {e}")
            result["description_error"] = str(e)
        
        return result
    
    def _get_timestamp(self) -> str:
        """Get formatted timestamp for description"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M")
    
    def enrich_case_iocs(
        self, 
        case_id: int,
        update_description: bool = True
    ) -> Dict[str, Any]:
        """
        Enrich tất cả IOCs trong một case
        
        Args:
            case_id: IRIS Case ID
            update_description: Whether to update IOC descriptions
        
        Returns:
            Results dict with per-IOC status
        """
        results = {
            "case_id": case_id,
            "total_iocs": 0,
            "enriched": 0,
            "failed": 0,
            "iocs": []
        }
        
        try:
            # Get all IOCs from case
            iocs = self.iris_service.get_case_iocs(case_id)
            results["total_iocs"] = len(iocs)
            
            for ioc in iocs:
                ioc_result = self.enrich_ioc_with_analysis(
                    case_id=case_id,
                    ioc_id=ioc['ioc_id'],
                    update_description=update_description
                )
                
                if ioc_result.get("status") == "success":
                    results["enriched"] += 1
                else:
                    results["failed"] += 1
                
                results["iocs"].append(ioc_result)
            
        except Exception as e:
            logger.error(f"Failed to enrich case {case_id}: {e}", exc_info=True)
            results["error"] = str(e)
        
        return results

# Singleton instance
_enrich_service = None

def get_enrich_service() -> EnrichService:
    """Get singleton EnrichService instance"""
    global _enrich_service
    if _enrich_service is None:
        _enrich_service = EnrichService()
    return _enrich_service
