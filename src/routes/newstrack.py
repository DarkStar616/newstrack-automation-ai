"""
Newstrack keyword processing routes with strict JSON schemas and guardrails.
"""
from flask import Blueprint, request, jsonify, current_app
import json
import time
from typing import Dict, List, Any, Optional
from src.utils.llm_client import get_llm_client

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
    
    Expected JSON input:
    {
        "sector": "string",
        "company": "string (optional)",
        "keywords": "string"
    }
    
    Expected JSON output:
    {
        "categories": {
            "industry": ["..."],
            "company": ["..."],
            "regulatory": ["..."]
        },
        "explanations": {
            "industry": "...",
            "company": "...",
            "regulatory": "..."
        }
    }
    """
    try:
        data = request.json
        error_response = validate_request_data(data, ['sector', 'keywords'])
        if error_response:
            return error_response
        
        sector = data['sector'].strip()
        company = data.get('company', '').strip()
        keywords = data['keywords'].strip()
        
        # Use company if provided, otherwise use sector
        company_or_sector = company if company else sector
        
        # Create strict JSON prompt
        prompt = f"""You are a keyword categorization expert. Categorize the following keywords into exactly three categories: industry, company, and regulatory.

SECTOR: {sector}
TARGET ORGANIZATION: {company_or_sector}

KEYWORDS TO CATEGORIZE:
{keywords}

INSTRUCTIONS:
1. Sort each keyword into one of these three categories:
   - industry: General industry terms, products, services, market segments
   - company: Specific company names, brands, organizations
   - regulatory: Laws, regulations, compliance terms, government bodies

2. Provide a brief explanation for each category's purpose.

3. Return ONLY valid JSON in this exact format:

{{
    "categories": {{
        "industry": ["keyword1", "keyword2"],
        "company": ["keyword3", "keyword4"],
        "regulatory": ["keyword5", "keyword6"]
    }},
    "explanations": {{
        "industry": "Brief explanation of industry category",
        "company": "Brief explanation of company category", 
        "regulatory": "Brief explanation of regulatory category"
    }}
}}

Do not include any text outside the JSON response."""

        # Get LLM client and make request
        llm_client = get_llm_client()
        response = llm_client.chat_completion([
            {"role": "user", "content": prompt}
        ], temperature=0.1)
        
        # Parse JSON response
        result = llm_client.parse_json_response(response)
        
        # Validate response structure
        if 'categories' not in result or 'explanations' not in result:
            return create_error_response(500, "Invalid response format from LLM")
        
        required_categories = ['industry', 'company', 'regulatory']
        for category in required_categories:
            if category not in result['categories']:
                result['categories'][category] = []
            if category not in result['explanations']:
                result['explanations'][category] = ""
        
        return jsonify({
            'success': True,
            'result': result,
            'step': 'categorize'
        })
        
    except Exception as e:
        current_app.logger.error(f"Categorize error: {str(e)}")
        return create_error_response(500, "Internal server error during categorization")


@newstrack_bp.route('/expand', methods=['POST'])
def expand_categories():
    """
    Step 2: Expand categories with additional relevant keywords.
    
    Expected JSON input:
    {
        "company_or_sector": "string",
        "step1_result": "object (result from categorize step)"
    }
    
    Expected JSON output:
    {
        "expanded": {
            "industry": ["original and new terms..."],
            "company": ["..."],
            "regulatory": ["..."]
        },
        "notes": "brief rationale of expansions"
    }
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
        
        # Create strict JSON prompt for expansion
        prompt = f"""You are a keyword expansion expert. Expand the existing keyword categories with additional relevant terms for {company_or_sector}.

EXISTING CATEGORIES:
{json.dumps(categories, indent=2)}

INSTRUCTIONS:
1. For each category (industry, company, regulatory), add 3-5 new relevant keywords
2. Keep ALL original keywords and add new ones
3. Focus on terms that would help find relevant news articles
4. Ensure new keywords are appropriate for the category

Return ONLY valid JSON in this exact format:

{{
    "expanded": {{
        "industry": ["all original terms plus new ones"],
        "company": ["all original terms plus new ones"],
        "regulatory": ["all original terms plus new ones"]
    }},
    "notes": "Brief explanation of expansion strategy and rationale"
}}

Do not include any text outside the JSON response."""

        # Get LLM client and make request
        llm_client = get_llm_client()
        response = llm_client.chat_completion([
            {"role": "user", "content": prompt}
        ], temperature=0.1)
        
        # Parse JSON response
        result = llm_client.parse_json_response(response)
        
        # Validate response structure
        if 'expanded' not in result:
            return create_error_response(500, "Invalid response format from LLM")
        
        # Ensure all categories exist
        required_categories = ['industry', 'company', 'regulatory']
        for category in required_categories:
            if category not in result['expanded']:
                result['expanded'][category] = categories.get(category, [])
        
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
    
    Expected JSON input:
    {
        "company_or_sector": "string",
        "date": "string",
        "step2_result": "object (result from expand step)"
    }
    
    Expected JSON output:
    {
        "updated": {
            "industry": ["..."],
            "company": ["..."],
            "regulatory": ["..."]
        },
        "removed": [
            {"term": "...", "reason": "..."}
        ],
        "justification": "brief notes tied to current date"
    }
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
        
        # Create strict JSON prompt for dropping outdated keywords
        prompt = f"""You are a keyword currency expert. Review the keyword list and remove any terms that may be outdated as of {date} for {company_or_sector}.

CURRENT KEYWORDS:
{json.dumps(expanded, indent=2)}

CURRENT DATE: {date}

INSTRUCTIONS:
1. Identify keywords that may be outdated, obsolete, or no longer relevant
2. Consider company mergers, rebrands, regulatory changes, market exits
3. Keep the majority of keywords - only remove clearly outdated ones
4. Provide specific reasons for each removal

Return ONLY valid JSON in this exact format:

{{
    "updated": {{
        "industry": ["remaining current terms"],
        "company": ["remaining current terms"],
        "regulatory": ["remaining current terms"]
    }},
    "removed": [
        {{"term": "outdated_keyword", "reason": "specific reason for removal"}},
        {{"term": "another_keyword", "reason": "another specific reason"}}
    ],
    "justification": "Brief explanation of removal criteria and date considerations"
}}

Do not include any text outside the JSON response."""

        # Get LLM client and make request
        llm_client = get_llm_client()
        response = llm_client.chat_completion([
            {"role": "user", "content": prompt}
        ], temperature=0.1)
        
        # Parse JSON response
        result = llm_client.parse_json_response(response)
        
        # Validate response structure
        if 'updated' not in result or 'removed' not in result:
            return create_error_response(500, "Invalid response format from LLM")
        
        # Ensure all categories exist
        required_categories = ['industry', 'company', 'regulatory']
        for category in required_categories:
            if category not in result['updated']:
                result['updated'][category] = expanded.get(category, [])
        
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
    
    Expected JSON input:
    {
        "sector": "string",
        "company": "string (optional)",
        "keywords": "string",
        "date": "string"
    }
    
    Returns results from all three steps.
    """
    try:
        data = request.json
        error_response = validate_request_data(data, ['sector', 'keywords', 'date'])
        if error_response:
            return error_response
        
        sector = data['sector'].strip()
        company = data.get('company', '').strip()
        keywords = data['keywords'].strip()
        date = data['date'].strip()
        
        company_or_sector = company if company else sector
        
        # Step 1: Categorize
        step1_data = {
            'sector': sector,
            'company': company,
            'keywords': keywords
        }
        
        # Simulate internal call to categorize
        with current_app.test_request_context(json=step1_data, method='POST'):
            step1_response = categorize_keywords()
            if step1_response[1] != 200:  # Check status code
                return step1_response
            step1_result = step1_response[0].get_json()['result']
        
        # Step 2: Expand
        step2_data = {
            'company_or_sector': company_or_sector,
            'step1_result': step1_result
        }
        
        with current_app.test_request_context(json=step2_data, method='POST'):
            step2_response = expand_categories()
            if step2_response[1] != 200:
                return step2_response
            step2_result = step2_response[0].get_json()['result']
        
        # Step 3: Drop
        step3_data = {
            'company_or_sector': company_or_sector,
            'date': date,
            'step2_result': step2_result
        }
        
        with current_app.test_request_context(json=step3_data, method='POST'):
            step3_response = drop_old_keywords()
            if step3_response[1] != 200:
                return step3_response
            step3_result = step3_response[0].get_json()['result']
        
        return jsonify({
            'success': True,
            'step1_result': step1_result,
            'step2_result': step2_result,
            'step3_result': step3_result,
            'final_result': step3_result
        })
        
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

