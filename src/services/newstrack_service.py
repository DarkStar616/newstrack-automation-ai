"""
Pure service functions for newstrack keyword processing.
These functions contain core business logic without Flask dependencies.
"""
import os
import json
from typing import Dict, List, Optional, Any
from src.utils.llm_client import get_llm_client
from src.utils.guardrails import get_guardrails_engine
from src.utils.perplexity_client import PerplexityClient
from src.utils.config import get_search_mode, get_perplexity_key, get_recency_window, get_max_results_for_mode


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
        Dictionary with expanded categories and guardrails
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
    
    # Apply guardrails to expanded results
    all_input_keywords = []
    for cat_list in categories.values():
        all_input_keywords.extend(cat_list)
    
    guardrails = get_guardrails_engine()
    guardrails_result = guardrails.apply_all_guardrails(all_input_keywords, result['expanded'])
    
    result['guardrails'] = guardrails_result['guardrails']
    
    return result


def do_drop(sector: str, company: Optional[str], current_date: str, categories: Dict[str, List[str]], 
            search_mode: Optional[str] = None, recency_window_months: Optional[int] = None, 
            max_results_per_keyword: Optional[int] = None) -> Dict[str, Any]:
    """
    Remove outdated keywords from the expanded list with optional evidence validation.
    
    Args:
        sector: The sector/industry context
        company: Optional company name  
        current_date: Current date for currency validation
        categories: Categories from expand step
        search_mode: Optional search mode ("off", "fast", "deep")
        recency_window_months: Optional recency window in months
        max_results_per_keyword: Optional max evidence results per keyword
        
    Returns:
        Dictionary with updated categories, removed keywords, evidence_refs, and guardrails
    """
    company_or_sector = company if company else sector
    
    # Initialize search configuration
    search_mode = search_mode or get_search_mode()
    # Force search mode in test mode for evidence gathering
    if os.getenv("SEARCH_TEST_MODE", "false").lower() == "true" and search_mode == "off":
        search_mode = "fast"
    recency_window_months = recency_window_months or get_recency_window()
    max_results_per_keyword = max_results_per_keyword or get_max_results_for_mode(search_mode)
    
    # Initialize Perplexity client for evidence gathering
    evidence_refs = {}
    perplexity_client = None
    
    if search_mode != "off":
        perplexity_key = get_perplexity_key()
        # In test mode, allow empty API key for stub evidence
        if perplexity_key or os.getenv("SEARCH_TEST_MODE", "false").lower() == "true":
            perplexity_client = PerplexityClient(perplexity_key or "test_key", search_mode)
    
    # Gather evidence for each keyword
    all_keywords = []
    for category_keywords in categories.values():
        all_keywords.extend(category_keywords)
    
    for keyword in all_keywords:
        if perplexity_client:
            evidence = perplexity_client.search_keyword(
                keyword, 
                max_results=max_results_per_keyword,
                recency_months=recency_window_months
            )
            if evidence:
                evidence_refs[keyword] = evidence
    
    # Create evidence-enhanced prompt for dropping outdated keywords
    if search_mode == "off":
        # Original prompt without evidence
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
    else:
        # Evidence-enhanced prompt
        evidence_summary = ""
        if evidence_refs:
            evidence_summary = "\nEVIDENCE GATHERED:\n"
            for keyword, evidence_list in evidence_refs.items():
                evidence_summary += f"\n{keyword}:\n"
                if evidence_list:
                    for i, evidence in enumerate(evidence_list[:3], 1):  # Limit to 3 per keyword
                        evidence_summary += f"  {i}. {evidence['title']} ({evidence['published_date']})\n"
                        evidence_summary += f"     {evidence['snippet'][:100]}...\n"
                else:
                    evidence_summary += "  No recent evidence found\n"
        
        prompt = f"""You are a keyword currency expert with access to recent web evidence. Review the keyword list and remove any terms that may be outdated as of {current_date} for {company_or_sector}.

CURRENT KEYWORDS:
{json.dumps(categories, indent=2)}

CURRENT DATE: {current_date}

{evidence_summary}

INSTRUCTIONS:
1. Use the evidence above to assess keyword relevance and currency
2. If no recent evidence is found for a keyword within {recency_window_months} months, consider removing it
3. Keep keywords with recent, relevant evidence
4. Consider company mergers, rebrands, regulatory changes, market exits
5. Provide specific reasons for each removal, referencing evidence when available

Return ONLY valid JSON in this exact format:

{{
    "updated": {{
        "industry": ["remaining current terms"],
        "company": ["remaining current terms"],
        "regulatory": ["remaining current terms"]
    }},
    "removed": [
        {{"term": "outdated_keyword", "reason": "specific reason for removal", "evidence_used": [1, 2]}},
        {{"term": "another_keyword", "reason": "another specific reason", "evidence_used": []}}
    ],
    "justification": "Brief explanation of removal criteria considering both evidence and date"
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
    
    # Apply guardrails to final results
    all_input_keywords = []
    for cat_list in categories.values():
        all_input_keywords.extend(cat_list)
    
    guardrails = get_guardrails_engine()
    guardrails_result = guardrails.apply_all_guardrails(all_input_keywords, result['updated'])
    
    result['guardrails'] = guardrails_result['guardrails']
    result['evidence_refs'] = evidence_refs
    
    return result