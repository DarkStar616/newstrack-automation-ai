"""
Newstrack keyword processing routes with strict JSON schemas and guardrails.
"""
from flask import Blueprint, request, jsonify, current_app
import json
import time
import os
from typing import Dict, List, Any, Optional, Tuple
from src.services.newstrack_service import do_categorize, do_expand, do_drop
from src.utils.audit import get_audit_logger
from src.utils.guardrails import enforce_isolation, load_guards

newstrack_bp = Blueprint('newstrack', __name__)


def create_error_response(code: int, message: str) -> tuple:
    """Create standardized error response."""
    return jsonify({
        "error": {
            "code": code,
            "message": message
        }
    }), code


def normalize_request_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize and validate request data with backward compatibility."""
    if not data:
        raise ValueError("Request body is required")
    
    # Backward compatibility: convert company_or_sector to sector+company
    if 'company_or_sector' in data and 'sector' not in data:
        data['sector'] = data['company_or_sector']
        data['company'] = data.get('company', '')
    
    # Normalize keywords: handle both string and array formats
    if 'keywords' in data:
        if isinstance(data['keywords'], str):
            data['keywords'] = [kw.strip() for kw in data['keywords'].split('\n') if kw.strip()]
        elif isinstance(data['keywords'], list):
            data['keywords'] = [str(kw).strip() for kw in data['keywords'] if str(kw).strip()]
    
    # Normalize categories: ensure it's a proper dictionary
    if 'categories' in data and isinstance(data['categories'], dict):
        for category in ['industry', 'company', 'regulatory']:
            if category not in data['categories']:
                data['categories'][category] = []
    
    # Handle date fields - accept both 'date' and 'current_date'
    if 'current_date' in data and 'date' not in data:
        data['date'] = data['current_date']
    
    return data


def validate_required_fields(data: Dict[str, Any], required_fields: List[str]) -> None:
    """Validate that required fields are present and non-empty."""
    for field in required_fields:
        if field not in data or not data[field]:
            raise ValueError(f"Field '{field}' is required")


def normalize_keywords(raw_keywords: Any) -> List[str]:
    """Normalize keywords from string or array format."""
    if isinstance(raw_keywords, str):
        return [kw.strip() for kw in raw_keywords.split('\n') if kw.strip()]
    elif isinstance(raw_keywords, list):
        return [str(kw).strip() for kw in raw_keywords if str(kw).strip()]
    else:
        return []


def dedupe_with_counts(keywords: List[str]) -> Dict[str, Any]:
    """Deduplicate keywords and return counts."""
    seen = set()
    unique = []
    duplicates = []
    
    for kw in keywords:
        if kw.lower() in seen:
            if kw not in duplicates:  # Only add first duplicate occurrence
                duplicates.append(kw)
        else:
            seen.add(kw.lower())
            unique.append(kw)
    
    return {
        'unique': unique,
        'duplicates_dropped_count': len(duplicates),
        'duplicates_dropped_list': duplicates
    }


@newstrack_bp.route('/categorize', methods=['POST'])
def categorize_keywords():
    """
    Step 1: Categorize keywords into industry, company, and regulatory categories.
    
    Accepts:
    - { "sector": str, "company": str, "keywords": str|array }
    - { "company_or_sector": str, "keywords": str|array } (backward compatible)
    
    Returns: { "categories": {...}, "explanations": {...}, "guardrails": {...} }
    """
    try:
        data = normalize_request_data(request.json or {})
        validate_required_fields(data, ['sector', 'keywords'])
        
        sector = data['sector'].strip()
        company = data.get('company', '').strip() or None
        raw_keywords = data['keywords']
        
        # Normalize and deduplicate keywords
        normalized_keywords = normalize_keywords(raw_keywords)
        if not normalized_keywords:
            return create_error_response(400, "No valid keywords provided")
        
        dedupe_result = dedupe_with_counts(normalized_keywords)
        unique_keywords = dedupe_result['unique']
        
        # Call service function with unique keywords
        result = do_categorize(sector, company, unique_keywords)
        
        # Apply isolation after service
        cleaned_categories, leaks_blocked = enforce_isolation(result['categories'])
        result['categories'] = cleaned_categories
        
        # Merge duplicate tracking and isolation into guardrails
        result['guardrails']['counts']['input_total'] = len(normalized_keywords)
        result['guardrails']['counts']['duplicates_dropped'] += dedupe_result['duplicates_dropped_count']
        result['guardrails']['counts']['leaks_blocked'] += len(leaks_blocked)
        result['guardrails']['duplicates_dropped'] = sorted(set(
            result['guardrails']['duplicates_dropped'] + dedupe_result['duplicates_dropped_list']
        ))
        result['guardrails']['leaks_blocked'] = sorted(set(
            result['guardrails']['leaks_blocked'] + leaks_blocked
        ))
        
        return jsonify({
            'categories': result['categories'],
            'explanations': result['explanations'],
            'guardrails': result['guardrails']
        })
        
    except ValueError as e:
        return create_error_response(400, str(e))
    except Exception as e:
        current_app.logger.error(f"Categorize error: {str(e)}")
        return create_error_response(500, "Internal server error during categorization")


@newstrack_bp.route('/expand', methods=['POST'])
def expand_categories():
    """
    Step 2: Expand categories with additional relevant keywords.
    
    Accepts:
    - { "sector": str, "company": str, "categories": {industry:[],company:[],regulatory:[]} }
    - { "company_or_sector": str, "categories": {...} } (backward compatible)
    
    Returns: { "expanded": {...}, "notes": "...", "guardrails": {...} }
    """
    try:
        data = normalize_request_data(request.json or {})
        validate_required_fields(data, ['sector', 'categories'])
        
        sector = data['sector'].strip()
        company = data.get('company', '').strip() or None
        categories = data['categories']
        
        if not isinstance(categories, dict):
            return create_error_response(400, "Categories must be an object with industry/company/regulatory keys")
        
        # Call service function
        result = do_expand(sector, company, categories)
        
        # Apply isolation after service
        cleaned_expanded, leaks_blocked = enforce_isolation(result['expanded'])
        result['expanded'] = cleaned_expanded
        
        # Update guardrails with isolation results
        result['guardrails']['counts']['leaks_blocked'] += len(leaks_blocked)
        result['guardrails']['leaks_blocked'] = sorted(set(
            result['guardrails']['leaks_blocked'] + leaks_blocked
        ))
        
        return jsonify({
            'expanded': result['expanded'],
            'notes': result['notes'],
            'guardrails': result['guardrails']
        })
        
    except ValueError as e:
        return create_error_response(400, str(e))
    except Exception as e:
        current_app.logger.error(f"Expand error: {str(e)}")
        return create_error_response(500, "Internal server error during expansion")


@newstrack_bp.route('/drop', methods=['POST'])
def drop_old_keywords():
    """
    Step 3: Remove outdated keywords from the expanded list.
    
    Accepts:
    - { "sector": str, "company": str, "date": str, "categories": {industry:[],company:[],regulatory:[]} }
    - { "company_or_sector": str, "current_date": str, "categories": {...} } (backward compatible)
    
    Returns: { "updated": {...}, "removed": [...], "justification": "...", "guardrails": {...} }
    """
    try:
        data = normalize_request_data(request.json or {})
        validate_required_fields(data, ['sector', 'date', 'categories'])
        
        sector = data['sector'].strip()
        company = data.get('company', '').strip() or None
        date = data['date'].strip()
        categories = data['categories']
        
        if not isinstance(categories, dict):
            return create_error_response(400, "Categories must be an object with industry/company/regulatory keys")
        
        # Extract optional search parameters
        search_mode = data.get('search_mode')
        recency_window_months = data.get('recency_window_months')
        max_results_per_keyword = data.get('max_results_per_keyword')
        
        # Call service function with search parameters
        result = do_drop(sector, company, date, categories, search_mode, recency_window_months, max_results_per_keyword)
        
        # Apply isolation before final result
        cleaned_updated, leaks_blocked = enforce_isolation(result['updated'])
        result['updated'] = cleaned_updated
        
        # Update guardrails with isolation results
        result['guardrails']['counts']['leaks_blocked'] += len(leaks_blocked)
        result['guardrails']['leaks_blocked'] = sorted(set(
            result['guardrails']['leaks_blocked'] + leaks_blocked
        ))
        
        return jsonify({
            'updated': result['updated'],
            'removed': result['removed'],
            'justification': result['justification'],
            'evidence_refs': result.get('evidence_refs', {}),
            'guardrails': result['guardrails']
        })
        
    except ValueError as e:
        return create_error_response(400, str(e))
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
        data = normalize_request_data(request.json or {})
        validate_required_fields(data, ['sector', 'keywords'])
        
        sector = data['sector'].strip()
        company = data.get('company', '').strip() or None
        raw_keywords = data['keywords']
        current_date = data.get('date', '2025-09').strip()
        
        # Extract optional search parameters
        search_mode = data.get('search_mode')
        recency_window_months = data.get('recency_window_months')
        max_results_per_keyword = data.get('max_results_per_keyword')
        
        # Normalize and deduplicate keywords
        normalized_keywords = normalize_keywords(raw_keywords)
        if not normalized_keywords:
            return create_error_response(400, "No valid keywords provided")
        
        dedupe_result = dedupe_with_counts(normalized_keywords)
        unique_keywords = dedupe_result['unique']
        
        # Step 1: Categorize with unique keywords
        categorize_result = do_categorize(sector, company, unique_keywords)
        
        # Merge duplicate tracking into guardrails
        categorize_result['guardrails']['counts']['input_total'] = len(normalized_keywords)
        categorize_result['guardrails']['counts']['duplicates_dropped'] += dedupe_result['duplicates_dropped_count']
        categorize_result['guardrails']['duplicates_dropped'] = sorted(set(
            categorize_result['guardrails']['duplicates_dropped'] + dedupe_result['duplicates_dropped_list']
        ))
        
        # Step 2: Expand using the processed categories from guardrails
        expand_result = do_expand(sector, company, categorize_result['processed_categories'])
        
        # Step 3: Drop using expanded categories with search parameters
        drop_result = do_drop(sector, company, current_date, expand_result['expanded'], 
                             search_mode, recency_window_months, max_results_per_keyword)
        
        # Apply final isolation before committing final_result
        final_cleaned, final_leaks_blocked = enforce_isolation(drop_result['updated'])
        drop_result['updated'] = final_cleaned
        
        # Update TOP-LEVEL guardrails with final isolation results
        categorize_result['guardrails']['counts']['leaks_blocked'] += len(final_leaks_blocked)
        categorize_result['guardrails']['leaks_blocked'] = sorted(set(
            categorize_result['guardrails']['leaks_blocked'] + final_leaks_blocked
        ))
        
        # Calculate processing time
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        # Write audit entry
        batch_id = None
        try:
            audit_logger = get_audit_logger()
            batch_id = audit_logger.generate_batch_id()
            
            audit_logger.write_batch_audit(
                batch_id=batch_id,
                category=sector,
                input_keywords=normalized_keywords,  # Use normalized for audit
                final_categories=drop_result['updated'],
                guardrails_result=categorize_result,  # Contains guardrails data with duplicates
                timing_ms=processing_time_ms,
                step='process-all',
                evidence_refs=drop_result.get('evidence_refs', {})
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
            'step2_result': {
                'expanded': expand_result['expanded'],
                'notes': expand_result['notes']
            },
            'step3_result': {
                'updated': drop_result['updated'],
                'removed': drop_result['removed'],
                'justification': drop_result['justification'],
                'evidence_refs': drop_result.get('evidence_refs', {})
            },
            'final_result': drop_result,
            'guardrails': categorize_result['guardrails'],
            'batch_id': batch_id,
            'timing_ms': processing_time_ms
        }
        
        return jsonify(combined_result)
        
    except ValueError as e:
        return create_error_response(400, str(e))
    except Exception as e:
        current_app.logger.error(f"Process-all error: {str(e)}")
        return create_error_response(500, "Internal server error during full processing")




@newstrack_bp.route('/healthz', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({"ok": True})


@newstrack_bp.route('/guards', methods=['GET'])
def get_guards_info():
    """
    Debug endpoint to show guard set information.
    Only available when DEBUG=true or LLM_TEST_MODE=true.
    """
    debug_mode = os.getenv('DEBUG', 'false').lower() == 'true'
    test_mode = os.getenv('LLM_TEST_MODE', 'false').lower() == 'true'
    
    if not (debug_mode or test_mode):
        return create_error_response(404, "Not found")
    
    try:
        guards = load_guards()
        
        sample = {}
        for category, guard_set in guards.items():
            # Get first 5 terms from each set
            sample[category] = sorted(list(guard_set))[:5]
        
        return jsonify({
            'industry_count': len(guards.get('industry', set())),
            'company_count': len(guards.get('company', set())),
            'regulatory_count': len(guards.get('regulatory', set())),
            'sample': sample
        })
        
    except Exception as e:
        current_app.logger.error(f"Guards info error: {str(e)}")
        return create_error_response(500, "Failed to retrieve guard information")


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

