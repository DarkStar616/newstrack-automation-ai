"""
Pure service functions for newstrack keyword processing.
These functions contain core business logic without Flask dependencies.
"""
import json
from typing import Dict, List, Optional, Any
from src.utils.llm_client import get_llm_client
from src.utils.guardrails import get_guardrails_engine


def do_categorize(sector: str, company: Optional[str], keywords: List[str]) -> Dict[str, Any]:
    """
    Categorize keywords into industry, company, and regulatory categories.
    
    Args:
        sector: The sector/industry context
        company: Optional company name
        keywords: List of keywords to categorize
        
    Returns:
        Dictionary with categories and explanations
    """
    company_or_sector = company if company else sector
    
    # Create prompt for categorization
    keywords_text = '\n'.join(keywords)
    prompt = f"""You are a keyword categorization expert. Categorize the following keywords into exactly three categories: industry, company, and regulatory.

SECTOR: {sector}
TARGET ORGANIZATION: {company_or_sector}

KEYWORDS TO CATEGORIZE:
{keywords_text}

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
    
    # Ensure all required categories exist
    required_categories = ['industry', 'company', 'regulatory']
    for category in required_categories:
        if 'categories' not in result:
            result['categories'] = {}
        if category not in result['categories']:
            result['categories'][category] = []
        if 'explanations' not in result:
            result['explanations'] = {}
        if category not in result['explanations']:
            result['explanations'][category] = ""
    
    # Apply guardrails
    guardrails = get_guardrails_engine()
    guardrails_result = guardrails.apply_all_guardrails(keywords, result['categories'])
    
    return {
        'categories': result['categories'],
        'explanations': result['explanations'],
        'processed_categories': guardrails_result['categories'],
        'guardrails': guardrails_result['guardrails']
    }


def do_expand(sector: str, company: Optional[str], categories: Dict[str, List[str]]) -> Dict[str, Any]:
    """
    Expand categories with additional relevant keywords.
    
    Args:
        sector: The sector/industry context
        company: Optional company name
        categories: Categories from categorize step
        
    Returns:
        Dictionary with expanded categories
    """
    company_or_sector = company if company else sector
    
    # Create prompt for expansion
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
    
    # Ensure all categories exist
    required_categories = ['industry', 'company', 'regulatory']
    for category in required_categories:
        if 'expanded' not in result:
            result['expanded'] = {}
        if category not in result['expanded']:
            result['expanded'][category] = categories.get(category, [])
    
    return result


def do_drop(sector: str, company: Optional[str], current_date: str, categories: Dict[str, List[str]]) -> Dict[str, Any]:
    """
    Remove outdated keywords from the expanded list.
    
    Args:
        sector: The sector/industry context
        company: Optional company name  
        current_date: Current date for currency validation
        categories: Categories from expand step
        
    Returns:
        Dictionary with updated categories and removed keywords
    """
    company_or_sector = company if company else sector
    
    # Create prompt for dropping outdated keywords
    prompt = f"""You are a keyword currency expert. Review the keyword list and remove any terms that may be outdated as of {current_date} for {company_or_sector}.

CURRENT KEYWORDS:
{json.dumps(categories, indent=2)}

CURRENT DATE: {current_date}

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
    
    # Ensure all categories exist
    required_categories = ['industry', 'company', 'regulatory']
    for category in required_categories:
        if 'updated' not in result:
            result['updated'] = {}
        if category not in result['updated']:
            result['updated'][category] = categories.get(category, [])
        if 'removed' not in result:
            result['removed'] = []
    
    return result