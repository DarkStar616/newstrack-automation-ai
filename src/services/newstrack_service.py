"""
Pure service functions for newstrack keyword processing.
These functions contain core business logic without Flask dependencies.
"""
import os
import json
from typing import Dict, List, Optional, Any, Union
from src.utils.llm_client import get_llm_client
from src.utils.guardrails import get_guardrails_engine
from src.utils.perplexity_client import PerplexityClient
from src.utils.config import get_search_mode, get_perplexity_key, get_recency_window, get_max_results_for_mode
from src.types.flags import Flag, create_flag, create_stale_flag, create_off_topic_flag, create_wrong_region_flag, create_wrong_domain_flag, create_weak_evidence_flag
from src.utils.region import get_scope_description, check_domain_fitness
from datetime import datetime, timedelta


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
            max_results_per_keyword: Optional[int] = None, source_location: Union[str, Dict[str, str], None] = None) -> Dict[str, Any]:
    """
    Flag problematic keywords instead of removing them. All keywords are kept with appropriate flags.
    
    Args:
        sector: The sector/industry context
        company: Optional company name  
        current_date: Current date for currency validation
        categories: Categories from expand step
        search_mode: Optional search mode ("off", "test", "shallow")
        recency_window_months: Optional recency window in months
        max_results_per_keyword: Optional max evidence results per keyword
        source_location: Optional Excel source location rule for region filtering
        
    Returns:
        Dictionary with updated categories (all kept), flags map, evidence_refs, and guardrails
        - updated: All input keywords kept, grouped by category
        - removed: Always empty list (for backward compatibility)
        - flags: Map of keyword -> list of flag objects
        - evidence_refs: Evidence gathered for each keyword
        - guardrails: Guardrails validation results
    """
    company_or_sector = company if company else sector
    
    # Initialize search configuration
    search_mode = search_mode or get_search_mode()
    recency_window_months = recency_window_months or get_recency_window()
    max_results_per_keyword = max_results_per_keyword or get_max_results_for_mode(search_mode)
    
    # Initialize search for evidence gathering
    evidence_refs = {}
    debug_queries = {}
    region_scope = {}
    
    # Gather evidence for each keyword using enhanced search abstraction
    all_keywords = []
    for category_keywords in categories.values():
        all_keywords.extend(category_keywords)
    
    # Process each keyword individually to track debug queries and region scope
    for keyword in all_keywords:
        # Resolve effective source_location for this keyword
        if isinstance(source_location, dict):
            # Per-keyword source location from CSV batch processing
            raw_source_location = source_location.get(keyword, "")
            
            # Handle both dict objects (from BatchService) and strings
            if isinstance(raw_source_location, dict):
                # Dict object from BatchService: {"region_mode": "GLOBAL", "country": "X"}
                region_mode = raw_source_location.get('region_mode', 'GLOBAL')
                country = raw_source_location.get('country')
                
                # Convert dict format to string parsing variables and effective_source_location
                if region_mode == 'GLOBAL' or not country:
                    region_scope[keyword] = "global"
                    effective_region_mode = "global"
                    effective_region_country = None
                    effective_source_location = ""  # Global scope
                elif region_mode == 'EXCLUDE':
                    region_scope[keyword] = f"exclude:{country}"
                    effective_region_mode = "exclude"
                    effective_region_country = country
                    effective_source_location = f"!{country}"  # Exclude format
                elif region_mode == 'INCLUDE':
                    region_scope[keyword] = f"include:{country}"
                    effective_region_mode = "include" 
                    effective_region_country = country
                    effective_source_location = country  # Include format
                else:
                    # Fallback for unknown region modes
                    region_scope[keyword] = "global"
                    effective_region_mode = "global"
                    effective_region_country = None
                    effective_source_location = ""  # Global scope
            else:
                # String from CSV or manual input - use existing parsing logic
                effective_source_location = raw_source_location or ""
                if not effective_source_location or effective_source_location.strip().lower() in ['', 'na', 'null', 'none']:
                    region_scope[keyword] = "global"
                    effective_region_mode = "global"
                    effective_region_country = None
                elif effective_source_location.strip().startswith('!'):
                    country = effective_source_location.strip()[1:].strip()
                    region_scope[keyword] = f"exclude:{country}" if country else "global"
                    effective_region_mode = "exclude"
                    effective_region_country = country
                else:
                    country = effective_source_location.strip()
                    region_scope[keyword] = f"include:{country}" if country else "global"
                    effective_region_mode = "include"
                    effective_region_country = country
        else:
            # Global source location (string or None)
            effective_source_location = source_location or ""
            if not effective_source_location or effective_source_location.strip().lower() in ['', 'na', 'null', 'none']:
                region_scope[keyword] = "global"
                effective_region_mode = "global"
                effective_region_country = None
            elif effective_source_location.strip().startswith('!'):
                country = effective_source_location.strip()[1:].strip()
                region_scope[keyword] = f"exclude:{country}" if country else "global"
                effective_region_mode = "exclude"
                effective_region_country = country
            else:
                country = effective_source_location.strip()
                region_scope[keyword] = f"include:{country}" if country else "global"
                effective_region_mode = "include"
                effective_region_country = country
        
        # Build debug query according to specification: BASE = "{sector} {keyword}"
        from src.utils.search_client import _build_region_aware_query
        debug_query = _build_region_aware_query(keyword, sector, effective_region_mode, effective_region_country)
        debug_queries[keyword] = debug_query
        
        # Gather evidence if search is enabled
        if search_mode != "off":
            from src.utils.search_client import search_for_evidence
            evidence = search_for_evidence(
                keyword, 
                recency_months=recency_window_months,
                max_results=max_results_per_keyword,
                search_mode=search_mode,
                sector=sector,
                source_location=effective_source_location
            )
            evidence_refs[keyword] = evidence  # Always store, even if empty
        else:
            evidence_refs[keyword] = []
    
    # Generate flags for all keywords based on evidence and analysis
    flags_map = {}
    
    # Calculate cutoff date for staleness
    try:
        cutoff_date = datetime.strptime(current_date + "-01", "%Y-%m-%d") - timedelta(days=recency_window_months * 30)
    except:
        cutoff_date = datetime.now() - timedelta(days=recency_window_months * 30)
    
    # Analyze each keyword and generate appropriate flags
    for keyword in all_keywords:
        keyword_flags = []
        evidence_list = evidence_refs.get(keyword, [])
        
        # Check for stale evidence
        if evidence_list:
            latest_evidence = None
            for evidence in evidence_list:
                try:
                    evidence_date = datetime.strptime(evidence['published_date'], "%Y-%m-%d")
                    if latest_evidence is None or evidence_date > latest_evidence:
                        latest_evidence = evidence_date
                except:
                    continue
            
            if latest_evidence and latest_evidence < cutoff_date:
                days_out = (datetime.now() - latest_evidence).days
                keyword_flags.append(create_stale_flag(days_out, evidence_idx=[0]))
        
        # Check for off-topic evidence (all evidence items are irrelevant)
        if evidence_list:
            relevant_count = 0
            problematic_indices = []
            
            for i, evidence in enumerate(evidence_list):
                # Simple relevance check - keyword appears in title or snippet
                title_lower = evidence.get('title', '').lower()
                snippet_lower = evidence.get('snippet', '').lower()
                keyword_lower = keyword.lower()
                
                if keyword_lower in title_lower or keyword_lower in snippet_lower:
                    relevant_count += 1
                else:
                    problematic_indices.append(i)
            
            # If no evidence is relevant, flag as off-topic
            if relevant_count == 0 and len(evidence_list) > 0:
                keyword_flags.append(create_off_topic_flag(
                    f"No evidence found relevant to {keyword}",
                    evidence_idx=list(range(len(evidence_list)))
                ))
        
        # Check for wrong domain (health vs P&C insurance)
        if evidence_list and sector and "short-term" in sector.lower():
            wrong_domain_indices = []
            for i, evidence in enumerate(evidence_list):
                is_wrong, reason = check_domain_fitness(
                    evidence.get('snippet', ''), 
                    evidence.get('title', ''), 
                    sector
                )
                if is_wrong:
                    wrong_domain_indices.append(i)
            
            if wrong_domain_indices:
                keyword_flags.append(create_wrong_domain_flag(
                    f"Evidence discusses health insurance, not P&C insurance",
                    evidence_idx=wrong_domain_indices
                ))
        
        # Check for region violations (if source_location is specified)
        if evidence_list and source_location:
            from src.utils.region import scope_allows
            region_violations = []
            
            # Get the effective source location for this keyword from our earlier processing
            keyword_region_scope = region_scope.get(keyword, "global")
            
            for i, evidence in enumerate(evidence_list):
                region_guess = evidence.get('region_guess')
                if region_guess and not scope_allows(keyword_region_scope, region_guess):
                    region_violations.append(i)
            
            if region_violations:
                scope_desc = get_scope_description(keyword_region_scope)
                keyword_flags.append(create_wrong_region_flag(
                    keyword_region_scope if keyword_region_scope != "global" else "Global",
                    region_guess if region_guess else "Unknown",
                    evidence_idx=region_violations
                ))
        
        # Check for weak evidence (all evidence items are problematic)
        if evidence_list:
            all_problematic = all(
                flag.type in ["off_topic", "wrong_region", "wrong_domain"] 
                for flag in keyword_flags
                if flag.evidence_idx
            )
            if all_problematic and len(keyword_flags) > 0:
                keyword_flags.append(create_weak_evidence_flag(
                    "All evidence items have quality issues"
                ))
        elif search_mode != "off":
            # No evidence found when evidence search was enabled
            keyword_flags.append(create_weak_evidence_flag(
                "No evidence found for this keyword"
            ))
        
        # Store flags for this keyword (even if empty)
        if keyword_flags:
            flags_map[keyword] = [flag.to_dict() for flag in keyword_flags]
    
    # ALL keywords are kept in updated - this is the key change
    updated_categories = categories.copy()  # Keep all input keywords
    
    # Build the result structure with the new flagging model
    result = {
        'updated': updated_categories,
        'removed': [],  # Always empty but kept for backward compatibility
        'flags': flags_map,  # New field mapping keywords to their flags
        'justification': f"All {len(all_keywords)} keywords retained with appropriate flags. "
                        f"Flagged {len(flags_map)} keywords with quality issues. "
                        f"Evidence evaluated for {len(evidence_refs)} keywords.",
        'evidence_refs': evidence_refs,
        'debug_queries': debug_queries,  # Queries built for each keyword
        'region_scope': region_scope  # Region scope for each keyword
    }
    
    # Apply guardrails to ensure we have the expected structure
    all_input_keywords = []
    for cat_list in categories.values():
        all_input_keywords.extend(cat_list)
    
    guardrails = get_guardrails_engine()
    guardrails_result = guardrails.apply_all_guardrails(all_input_keywords, result['updated'])
    
    # Update guardrails to reflect the new flagging model
    guardrails_result['guardrails']['counts']['output_accounted'] = len(all_input_keywords)  # All keywords accounted for
    guardrails_result['guardrails']['counts']['flags_total'] = sum(len(flags) for flags in flags_map.values())
    guardrails_result['guardrails']['completeness_check']['is_complete'] = True  # All keywords are kept
    guardrails_result['guardrails']['completeness_check']['missing_keywords'] = []  # No keywords missing
    
    result['guardrails'] = guardrails_result['guardrails']
    
    return result