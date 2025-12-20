"""
IOC Enrichment API Routes
"""
from flask import Blueprint, request, jsonify
from app.services.iris_service import IRISService
from app.services.llm_service import LLMService
from app.middleware.auth import require_api_key

ioc_bp = Blueprint('ioc', __name__)


@ioc_bp.route('/api/enrich/explain_intelowl', methods=['POST'])
@require_api_key('enrich:explain')
def explain_intelowl():
    """
    Lấy IntelOwl results từ IRIS và dùng AI giải thích
    
    Request:
    {
        "case_id": 1,
        "ioc_id": 199,
        "update_description": true  // optional, default: true
    }
    """
    data = request.json
    case_id = data['case_id']
    ioc_id = data['ioc_id']
    update_description = data.get('update_description', True)
    
    # 1. Lấy IntelOwl report từ IRIS
    iris_svc = IRISService()
    intelowl_data = iris_svc.get_ioc_intelowl_report(case_id, ioc_id)
    
    if not intelowl_data:
        return jsonify({
            "status": "error",
            "message": "No IntelOwl report found. Please run IntelOwl module first."
        }), 404
    
    # 2. Extract raw JSON
    raw_results = intelowl_data['raw_data']
    
    # Debug
    print(f"\n[DEBUG ROUTE] IntelOwl data keys: {intelowl_data.keys()}")
    print(f"[DEBUG ROUTE] HTML report length: {len(intelowl_data.get('html_report', ''))}")
    print(f"[DEBUG ROUTE] Raw results: {raw_results}")
    
    if not raw_results:
        return jsonify({
            "status": "error", 
            "message": "Cannot extract raw JSON from HTML report",
            "debug": {
                "html_preview": intelowl_data.get('html_report', '')[:200]
            }
        }), 400
    
    # 3. AI analysis
    llm_svc = LLMService()
    ai_analysis = llm_svc.explain_intelowl_results(
        ioc_value=intelowl_data['ioc_value'],
        raw_results=raw_results
    )
    
    # 4. Update IRIS với AI analysis (add comment)
    comment_text = f"[SmartXDR AI Analysis]\n\n{ai_analysis['summary']}"
    iris_svc.add_ioc_comment(
        case_id=case_id,
        ioc_id=ioc_id,
        comment=comment_text
    )
    
    # 5. Update IOC description với summary (nếu enabled)
    description_updated = False
    if update_description:
        try:
            # Summarize the analysis for description (max 1000 chars)
            summary = llm_svc.summarize_for_ioc_description(comment_text, max_length=1000)
            
            if summary:
                # Get current IOC description (để append, không ghi đè)
                ioc_data = iris_svc.get_ioc(case_id, ioc_id)
                current_desc = ioc_data.get('ioc_description', '') or ''
                
                # Build new description
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                smartxdr_summary = f"[SmartXDR {timestamp}] {summary}"
                
                if current_desc.strip():
                    new_desc = f"{current_desc}\n\n{smartxdr_summary}"
                else:
                    new_desc = smartxdr_summary
                
                # Update IOC
                iris_svc.update_ioc(
                    case_id=case_id,
                    ioc_id=ioc_id,
                    description=new_desc
                )
                description_updated = True
                print(f"[INFO] Updated IOC {ioc_id} description")
        except Exception as e:
            print(f"[WARNING] Failed to update IOC description: {e}")
    
    return jsonify({
        "status": "success",
        "summary": ai_analysis['summary'],
        "risk_level": ai_analysis['risk_level'],
        "recommendations": ai_analysis['recommendations'],
        "description_updated": description_updated
    })


@ioc_bp.route('/api/enrich/explain_case_iocs', methods=['POST'])
@require_api_key('enrich:explain')
def explain_case_iocs():
    """
    Phân tích tất cả IOCs trong một case với AI
    
    Request:
    {
        "case_id": 1,
        "skip_already_analyzed": true  // optional, default: true
    }
    
    Response:
    {
        "status": "success",
        "case_id": 1,
        "total_iocs": 5,
        "processed": 4,
        "skipped": 1,
        "failed": 0,
        "results": [...]
    }
    """
    data = request.json
    case_id = data.get('case_id')
    skip_already_analyzed = data.get('skip_already_analyzed', True)
    
    if not case_id:
        return jsonify({
            "status": "error",
            "message": "Missing required field: case_id"
        }), 400
    
    # Initialize services
    iris_svc = IRISService()
    llm_svc = LLMService()
    
    try:
        # 1. Get all IOCs from case
        iocs = iris_svc.get_case_iocs(case_id)
        
        if not iocs:
            return jsonify({
                "status": "success",
                "case_id": case_id,
                "total_iocs": 0,
                "processed": 0,
                "skipped": 0,
                "failed": 0,
                "results": [],
                "message": "No IOCs found in this case"
            }), 200
        
        # 2. Process each IOC
        results = []
        processed_count = 0
        skipped_count = 0
        failed_count = 0
        
        for ioc in iocs:
            ioc_id = ioc['ioc_id']
            ioc_value = ioc['ioc_value']
            
            result_entry = {
                "ioc_id": ioc_id,
                "ioc_value": ioc_value,
                "ioc_type": ioc['ioc_type']
            }
            
            try:
                # Get IntelOwl report
                intelowl_data = iris_svc.get_ioc_intelowl_report(case_id, ioc_id)
                
                if not intelowl_data or not intelowl_data.get('raw_data'):
                    result_entry['status'] = 'skipped'
                    result_entry['reason'] = 'No IntelOwl report found'
                    skipped_count += 1
                    results.append(result_entry)
                    continue
                
                # AI analysis
                ai_analysis = llm_svc.explain_intelowl_results(
                    ioc_value=ioc_value,
                    raw_results=intelowl_data['raw_data']
                )
                
                # Add comment to IRIS
                comment_text = f"[SmartXDR AI Analysis]\n\n{ai_analysis['summary']}"
                
                iris_svc.add_ioc_comment(
                    case_id=case_id,
                    ioc_id=ioc_id,
                    comment=comment_text
                )
                
                # Update IOC description with summary
                description_updated = False
                try:
                    summary = llm_svc.summarize_for_ioc_description(comment_text, max_length=1000)
                    if summary:
                        ioc_data = iris_svc.get_ioc(case_id, ioc_id)
                        current_desc = ioc_data.get('ioc_description', '') or ''
                        
                        from datetime import datetime
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                        smartxdr_summary = f"[SmartXDR {timestamp}] {summary}"
                        
                        new_desc = f"{current_desc}\n\n{smartxdr_summary}" if current_desc.strip() else smartxdr_summary
                        
                        iris_svc.update_ioc(case_id=case_id, ioc_id=ioc_id, description=new_desc)
                        description_updated = True
                except Exception as desc_e:
                    print(f"[WARNING] Failed to update IOC {ioc_id} description: {desc_e}")
                
                result_entry['status'] = 'success'
                result_entry['risk_level'] = ai_analysis['risk_level']
                result_entry['summary'] = ai_analysis['summary'][:200] + "..."  # Truncate for response
                result_entry['description_updated'] = description_updated
                processed_count += 1
                results.append(result_entry)
                
            except Exception as e:
                result_entry['status'] = 'failed'
                result_entry['error'] = str(e)
                failed_count += 1
                results.append(result_entry)
                print(f"[ERROR] Failed to process IOC {ioc_id} ({ioc_value}): {e}")
        
        return jsonify({
            "status": "success",
            "case_id": case_id,
            "total_iocs": len(iocs),
            "processed": processed_count,
            "skipped": skipped_count,
            "failed": failed_count,
            "results": results
        }), 200
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Failed to process case IOCs: {str(e)}"
        }), 500


@ioc_bp.route('/api/enrich/case_ioc_comments', methods=['GET'])
@require_api_key('enrich:read')
def get_case_ioc_comments():
    """
    Lấy comment mới nhất của SmartXDR cho mỗi IOC trong case
    
    Request:
    {
        "case_id": 52
    }
    
    Response:
    {
        "status": "success",
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
                    "comment_text": "[SmartXDR AI Analysis]\\n\\n...",
                    "comment_date": "2025-12-01T14:30:00",
                    "comment_user": "SmartXDR"
                }
            },
            ...
        ]
    }
    """
    data = request.json
    case_id = data.get('case_id')
    
    if not case_id:
        return jsonify({
            "status": "error",
            "message": "Missing required field: case_id"
        }), 400
    
    try:
        iris_svc = IRISService()
        result = iris_svc.get_case_ioc_smartxdr_comments(case_id)
        
        return jsonify({
            "status": "success",
            **result
        }), 200
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Failed to get case IOC comments: {str(e)}"
        }), 500