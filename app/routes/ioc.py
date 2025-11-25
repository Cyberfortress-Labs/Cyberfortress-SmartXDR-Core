"""
IOC Enrichment API Routes
"""
from flask import Blueprint, request, jsonify
from app.services.iris_service import IRISService
from app.services.llm_service import LLMService

ioc_bp = Blueprint('ioc', __name__)


@ioc_bp.route('/api/enrich/explain_intelowl', methods=['POST'])
def explain_intelowl():
    """
    Lấy IntelOwl results từ IRIS và dùng AI giải thích
    
    Request:
    {
        "case_id": 1,
        "ioc_id": 199
    }
    """
    data = request.json
    case_id = data['case_id']
    ioc_id = data['ioc_id']
    
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
    print(f"[DEBUG ROUTE] HTML report first 500 chars: {intelowl_data.get('html_report', '')[:500]}")
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
    iris_svc.add_ioc_comment(
        case_id=case_id,
        ioc_id=ioc_id,
        comment=f"[SmartXDR AI Analysis]\n\n{ai_analysis['summary']}"
    )
    
    return jsonify({
        "status": "success",
        "summary": ai_analysis['summary'],
        "risk_level": ai_analysis['risk_level'],
        "recommendations": ai_analysis['recommendations']
    })