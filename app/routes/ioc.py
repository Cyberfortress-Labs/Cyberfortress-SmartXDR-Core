"""
IOC Enrichment API Routes
"""
from flask import Blueprint, request, jsonify
from app.services.iris_service import IRISService
from app.services.llm_service import LLMService
from app.middleware.auth import require_api_key
from app.utils.logger import ioc_route_logger as logger

ioc_bp = Blueprint('ioc', __name__)


@ioc_bp.route('/api/enrich/explain_intelowl', methods=['POST'])
@require_api_key('enrich:explain')
def explain_intelowl():
    """
    Lấy IntelOwl/MISP results từ IRIS và dùng AI giải thích
    Fallback: Nếu không có IntelOwl, sử dụng MISP report
    
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
    
    iris_svc = IRISService()
    llm_svc = LLMService()
    
    # Track data source
    data_source = None
    raw_results = None
    ioc_value = None
    ai_analysis = None
    
    # 1. Try IntelOwl first
    intelowl_data = iris_svc.get_ioc_intelowl_report(case_id, ioc_id)
    
    if intelowl_data and intelowl_data.get('raw_data'):
        # Use IntelOwl data
        data_source = "IntelOwl"
        raw_results = intelowl_data['raw_data']
        ioc_value = intelowl_data['ioc_value']
        
        logger.info(f"\nUsing IntelOwl data for IOC {ioc_id}")
        logger.info(f"IntelOwl data keys: {intelowl_data.keys()}")
        logger.info(f"HTML report length: {len(intelowl_data.get('html_report', ''))}")
        
        # AI analysis with IntelOwl
        ai_analysis = llm_svc.explain_intelowl_results(
            ioc_value=ioc_value,
            raw_results=raw_results
        )
    else:
        # 2. Fallback to MISP
        logger.info(f"\n[DEBUG ROUTE] No IntelOwl report, trying MISP fallback for IOC {ioc_id}")
        
        misp_data = iris_svc.get_ioc_misp_report(case_id, ioc_id)
        
        if misp_data and misp_data.get('raw_data'):
            # Use MISP data
            data_source = "MISP"
            raw_results = misp_data['raw_data']
            ioc_value = misp_data['ioc_value']
            
            logger.info(f"[DEBUG ROUTE] Using MISP data for IOC {ioc_id}")
            logger.info(f"[DEBUG ROUTE] MISP raw_data type: {type(raw_results)}")
            
            # AI analysis with MISP
            ai_analysis = llm_svc.explain_misp_results(
                ioc_value=ioc_value,
                raw_results=raw_results
            )
        else:
            # No data available
            return jsonify({
                "status": "error",
                "message": "No enrichment data found. Please run IntelOwl or MISP module first."
            }), 404
    
    # 3. Add comment to IRIS
    source_label = f"[SmartXDR AI Analysis - {data_source}]"
    comment_text = f"{source_label}\n\n{ai_analysis['summary']}"
    iris_svc.add_ioc_comment(
        case_id=case_id,
        ioc_id=ioc_id,
        comment=comment_text
    )
    
    # 5. Update IOC description với summary (nếu enabled)
    description_updated = False
    logger.info(f"update_description={update_description}")
    if update_description:
        try:
            # Summarize the analysis for description (max 1000 chars)
            logger.info(f"Calling summarize_for_ioc_description with text length: {len(comment_text)}")
            summary = llm_svc.summarize_for_ioc_description(comment_text, max_length=1000)
            logger.info(f"summary returned: {type(summary)}, length: {len(summary) if summary else 0}")
            logger.info(f"summary preview: {summary[:200] if summary else 'EMPTY/NONE'}")
            
            if summary:
                # 1. Get current IOC data (để lấy description và tags)
                ioc_data = iris_svc.get_ioc(case_id, ioc_id)
                current_desc = ioc_data.get('ioc_description', '') or ''
                current_tags = ioc_data.get('ioc_tags', '') or ''
                
                # 2. Build SmartXDR section
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                risk_label = f"[{ai_analysis['risk_level']}]"
                smartxdr_header = f"--- [SmartXDR AI Analysis {timestamp}] {risk_label} ---"
                smartxdr_summary = f"{smartxdr_header}\n{summary}"
                
                # 3. Clean old SmartXDR summaries để tránh trùng lặp
                # Tìm và loại bỏ các đoạn cũ bắt đầu bằng --- [SmartXDR AI Analysis ... ---
                import re
                cleaned_desc = re.sub(r'--- \[SmartXDR AI Analysis .*? ---.*?(\n\n|$)', '', current_desc, flags=re.DOTALL).strip()
                
                # 4. Prepend new summary (đưa lên đầu cho dễ thấy)
                if cleaned_desc:
                    new_desc = f"{smartxdr_summary}\n\n{cleaned_desc}"
                else:
                    new_desc = smartxdr_summary
                
                # 5. Handle Tags
                tags_list = [t.strip() for t in current_tags.split(',') if t.strip()]
                
                # Add standard tags including data source
                new_tags = ['smartxdr-analyzed', f"risk:{ai_analysis['risk_level'].lower()}", f"source:{data_source.lower()}"]
                for tag in new_tags:
                    if tag not in tags_list:
                        tags_list.append(tag)
                
                # Update IOC
                logger.info(f"Calling update_ioc with description length: {len(new_desc)}")
                logger.info(f"Tags to update: {','.join(tags_list)}")
                result = iris_svc.update_ioc(
                    case_id=case_id,
                    ioc_id=ioc_id,
                    description=new_desc,
                    tags=",".join(tags_list)
                )
                logger.info(f"update_ioc result: {result}")
                description_updated = True
                logger.info(f" Updated IOC {ioc_id} description and tags")
        except Exception as e:
            logger.error(f"Failed to update IOC metadata: {e}")
            import traceback
            traceback.print_exc()
    
    return jsonify({
        "status": "success",
        "summary": ai_analysis['summary'],
        "risk_level": ai_analysis['risk_level'],
        "recommendations": ai_analysis['recommendations'],
        "description_updated": description_updated,
        "data_source": data_source
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
                    logger.error(f"Failed to update IOC {ioc_id} description: {desc_e}")
                
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
                logger.error(f"Failed to process IOC {ioc_id} ({ioc_value}): {e}")
        
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