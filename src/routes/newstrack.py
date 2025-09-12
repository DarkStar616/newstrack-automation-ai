"""
Newstrack keyword processing routes with strict JSON schemas and guardrails.
"""
from flask import Blueprint, request, jsonify, current_app
import json
import time
from typing import Dict, List, Any, Optional
from src.services.newstrack_service import do_categorize, do_expand, do_drop
from src.utils.audit import get_audit_logger

newstrack_bp = Blueprint('newstrack', __name__)


def create_error_response(code: int, message: str) -> tuple:
    """Create standardized error response."""
    return jsonify({
        "error": {
            "code": code,
            "message": message
        }
    }), code


def validate_request_data(data: Dict[str, Any], required_fields: List[str]) -> Optional[tuple]:
    """Validate request data and return error response if invalid."""
    if not data:
        return create_error_response(400, "Request body is required")
    
    for field in required_fields:
        if field not in data or not data[field]:
            return create_error_response(400, f"Field '{field}' is required")
    
    return None


@newstrack_bp.route('/categorize', methods=['POST'])
def categorize_keywords():
    """
    Step 1: Categorize keywords into industry, company, and regulatory categories.
    """
    try:
        data = request.json
        error_response = validate_request_data(data, ['sector', 'keywords'])
        if error_response:
            return error_response
        
        sector = data['sector'].strip()
        company = data.get('company', '').strip() or None
        keywords_text = data['keywords'].strip()
        
        # Parse keywords into list
        keywords = [kw.strip() for kw in keywords_text.split('\n') if kw.strip()]
        
        # Call service function
        result = do_categorize(sector, company, keywords)
        
        return jsonify({
            'success': True,
            'result': {
                'categories': result['categories'],
                'explanations': result['explanations']
            },
            'categories': result['processed_categories'],  
            'guardrails': result['guardrails'],
            'step': 'categorize'
        })
        
    except Exception as e:
        current_app.logger.error(f"Categorize error: {str(e)}")
        return create_error_response(500, "Internal server error during categorization")


@newstrack_bp.route('/expand', methods=['POST'])
def expand_categories():
    """
    Step 2: Expand categories with additional relevant keywords.
    """
    try:
        data = request.json
        error_response = validate_request_data(data, ['company_or_sector', 'step1_result'])
        if error_response:
            return error_response
        
        company_or_sector = data['company_or_sector'].strip()
        step1_result = data['step1_result']
        
        # Validate step1_result structure
        if 'categories' not in step1_result:
            return create_error_response(400, "Invalid step1_result: missing 'categories'")
        
        categories = step1_result['categories']
        
        # Parse company_or_sector into sector and company
        sector = company_or_sector
        company = None
        
        # Call service function
        result = do_expand(sector, company, categories)
        
        return jsonify({
            'success': True,
            'result': result,
            'step': 'expand'
        })
        
    except Exception as e:
        current_app.logger.error(f"Expand error: {str(e)}")
        return create_error_response(500, "Internal server error during expansion")


@newstrack_bp.route('/drop', methods=['POST'])
def drop_old_keywords():
    """
    Step 3: Remove outdated keywords from the expanded list.
    """
    try:
        data = request.json
        error_response = validate_request_data(data, ['company_or_sector', 'date', 'step2_result'])
        if error_response:
            return error_response
        
        company_or_sector = data['company_or_sector'].strip()
        date = data['date'].strip()
        step2_result = data['step2_result']
        
        # Validate step2_result structure
        if 'expanded' not in step2_result:
            return create_error_response(400, "Invalid step2_result: missing 'expanded'")
        
        expanded = step2_result['expanded']
        
        # Parse company_or_sector into sector and company
        sector = company_or_sector
        company = None
        
        # Call service function
        result = do_drop(sector, company, date, expanded)
        
        return jsonify({
            'success': True,
            'result': result,
            'step': 'drop'
        })
        
    except Exception as e:
        current_app.logger.error(f"Drop error: {str(e)}")
        return create_error_response(500, "Internal server error during keyword dropping")


@newstrack_bp.route('/process-all', methods=['POST'])
def process_all_steps():
    """
    Process all three steps in sequence: categorize, expand, drop.
    Writes audit entries and updates manifest on success.
    """
    start_time = time.time()
    try:
        data = request.json
        error_response = validate_request_data(data, ['sector', 'keywords'])
        if error_response:
            return error_response
        
        sector = data['sector'].strip()
        company = data.get('company', '').strip() or None
        keywords_input = data['keywords']
        current_date = data.get('date', data.get('current_date', '2025-09')).strip()
        
        # Parse keywords into list (handle both string and array formats)
        if isinstance(keywords_input, str):
            keywords = [kw.strip() for kw in keywords_input.split('\n') if kw.strip()]
        elif isinstance(keywords_input, list):
            keywords = [str(kw).strip() for kw in keywords_input if str(kw).strip()]
        else:
            return create_error_response(400, "Keywords must be a string or array")
        
        if not keywords:
            return create_error_response(400, "No valid keywords provided")
        
        # Step 1: Categorize
        categorize_result = do_categorize(sector, company, keywords)
        
        # Step 2: Expand using the processed categories from guardrails
        expand_result = do_expand(sector, company, categorize_result['processed_categories'])
        
        # Step 3: Drop using expanded categories
        drop_result = do_drop(sector, company, current_date, expand_result['expanded'])
        
        # Calculate processing time
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        # Write audit entry
        try:
            audit_logger = get_audit_logger()
            batch_id = audit_logger.generate_batch_id()
            
            audit_logger.write_batch_audit(
                batch_id=batch_id,
                category=sector,
                input_keywords=keywords,
                final_categories=drop_result['updated'],
                guardrails_result=categorize_result,  # Contains guardrails data
                timing_ms=processing_time_ms,
                step='process-all'
            )
            
        except Exception as e:
            current_app.logger.warning(f"Failed to write audit entry: {e}")
        
        # Combine all results 
        combined_result = {
            'success': True,
            'step1_result': {
                'categories': categorize_result['categories'],
                'explanations': categorize_result['explanations']
            },
            'step2_result': expand_result,
            'step3_result': drop_result,
            'final_result': drop_result,
            'guardrails': categorize_result['guardrails'],
            'batch_id': batch_id if 'batch_id' in locals() else None,
            'timing_ms': processing_time_ms
        }
        
        return jsonify(combined_result)
        
    except Exception as e:
        current_app.logger.error(f"Process-all error: {str(e)}")
        return create_error_response(500, "Internal server error during full processing")




@newstrack_bp.route('/healthz', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({"ok": True})


@newstrack_bp.route('/status', methods=['GET'])
def get_status():
    """
    Get system status including latest manifest summary.
    
    Returns:
        JSON with system status and processing statistics
    """
    try:
        from src.utils.audit import get_audit_logger
        
        audit_logger = get_audit_logger()
        manifest = audit_logger.get_latest_manifest()
        
        if manifest:
            return jsonify({
                "status": "operational",
                "manifest": manifest,
                "timestamp": time.time()
            })
        else:
            return jsonify({
                "status": "operational",
                "manifest": None,
                "message": "No processing history available",
                "timestamp": time.time()
            })
            
    except Exception as e:
        current_app.logger.error(f"Status endpoint error: {str(e)}")
        return create_error_response(500, "Failed to retrieve status information")

