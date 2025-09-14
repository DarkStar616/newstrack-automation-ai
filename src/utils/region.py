"""
Region inference and scope validation utilities.
Handles geographic filtering and validation based on Source location rules.
"""
import re
from typing import Optional, Dict, Set
from urllib.parse import urlparse


# Region mappings based on TLD and domain patterns
TLD_REGION_MAP = {
    '.za': 'South Africa',
    '.co.za': 'South Africa', 
    '.org.za': 'South Africa',
    '.gov.za': 'South Africa',
    '.ac.za': 'South Africa',
    '.us': 'United States',
    '.com': None,  # Too generic
    '.uk': 'United Kingdom',
    '.co.uk': 'United Kingdom',
    '.ca': 'Canada',
    '.au': 'Australia',
    '.com.au': 'Australia',
    '.de': 'Germany',
    '.fr': 'France',
    '.in': 'India',
    '.co.in': 'India',
    '.br': 'Brazil',
    '.com.br': 'Brazil'
}

# Domain-specific mappings for known hosts
DOMAIN_REGION_MAP = {
    'moneyweb.co.za': 'South Africa',
    'businesslive.co.za': 'South Africa', 
    'news24.com': 'South Africa',
    'iol.co.za': 'South Africa',
    'dailymaverick.co.za': 'South Africa',
    'fin24.com': 'South Africa',
    'timeslive.co.za': 'South Africa',
    'businesstech.co.za': 'South Africa',
    'mg.co.za': 'South Africa',
    'citizen.co.za': 'South Africa',
    'insurancechat.co.za': 'South Africa',
    'cover.co.za': 'South Africa',
    
    # International domains
    'reuters.com': 'Global',
    'bloomberg.com': 'Global', 
    'wsj.com': 'United States',
    'ft.com': 'United Kingdom',
    'bbc.com': 'United Kingdom',
    'cnn.com': 'United States',
    'forbes.com': 'United States',
    'insurancejournal.com': 'United States',
    'property-casualty360.com': 'United States',
    'insurancebusinessmag.com': 'Global'
}

# Keywords that indicate specific regions in content
REGION_KEYWORDS = {
    'South Africa': [
        'south africa', 'sa', 'johannesburg', 'cape town', 'durban', 'pretoria',
        'fsa', 'fsca', 'financial sector conduct authority', 'prudential authority',
        'rand', 'zar', 'sarb', 'reserve bank', 'sars'
    ],
    'United States': [
        'united states', 'usa', 'us', 'america', 'new york', 'california', 'texas',
        'naic', 'state insurance', 'department of insurance', 'fed', 'federal reserve',
        'dollar', 'usd', 'sec', 'treasury'
    ],
    'United Kingdom': [
        'united kingdom', 'uk', 'britain', 'england', 'london', 'scotland', 'wales',
        'fca', 'pra', 'boe', 'bank of england', 'pound', 'gbp', 'hmrc'
    ]
}


def infer_region(url: str, snippet: str, title: str) -> Optional[str]:
    """
    Infer the region from URL, snippet, and title.
    
    Args:
        url: The URL of the evidence source
        snippet: Text snippet or description
        title: Title of the article/source
        
    Returns:
        Region name if detected, None if unclear
    """
    if not url:
        return None
        
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # Check domain-specific mappings first
        if domain in DOMAIN_REGION_MAP:
            region = DOMAIN_REGION_MAP[domain]
            return region if region != 'Global' else None
            
        # Check TLD mappings
        for tld, region in TLD_REGION_MAP.items():
            if domain.endswith(tld) and region:
                return region
                
        # Check content for region keywords
        content = f"{title} {snippet}".lower()
        region_scores = {}
        
        for region, keywords in REGION_KEYWORDS.items():
            score = 0
            for keyword in keywords:
                if keyword in content:
                    # Weight longer keywords higher
                    score += len(keyword.split())
            
            if score > 0:
                region_scores[region] = score
        
        # Return the region with highest score if significant
        if region_scores:
            best_region = max(region_scores.items(), key=lambda x: x[1])
            if best_region[1] >= 2:  # At least 2 keyword matches
                return best_region[0]
                
    except Exception:
        pass
        
    return None


def scope_allows(expected_rule: str, actual_region: Optional[str]) -> bool:
    """
    Check if the actual region satisfies the Source location rule.
    
    Args:
        expected_rule: Source location rule from Excel:
            - "" (blank): include all regions
            - "South Africa": include only content from South Africa  
            - "!South Africa": include all regions except South Africa
        actual_region: The inferred region from evidence
        
    Returns:
        True if the region is allowed by the rule
    """
    if not expected_rule or expected_rule.strip() == "":
        # Blank rule means include all regions
        return True
        
    if expected_rule.startswith("!"):
        # Exclude rule - allow everything except the specified region
        excluded_region = expected_rule[1:].strip()
        return actual_region != excluded_region
    else:
        # Include rule - only allow the specified region (or unknown)
        required_region = expected_rule.strip()
        return actual_region is None or actual_region == required_region


def get_scope_description(source_location: str) -> str:
    """
    Get a human-readable description of the source location scope.
    
    Args:
        source_location: The Source location value from Excel
        
    Returns:
        Human-readable scope description for UI
    """
    if not source_location or source_location.strip() == "":
        return "Global"
    elif source_location.startswith("!"):
        excluded = source_location[1:].strip()
        return f"Global ({excluded} excluded)"
    else:
        return f"{source_location.strip()} only"


def filter_evidence_by_region(
    evidence_list: list, 
    source_location: str,
    keep_fallback: bool = True
) -> tuple[list, list]:
    """
    Filter evidence list based on source location rule.
    
    Args:
        evidence_list: List of evidence items with region_guess field
        source_location: Source location rule from Excel
        keep_fallback: If True, keep best global evidence when no matches found
        
    Returns:
        Tuple of (filtered_evidence, violations) where violations are items that don't match
    """
    if not source_location or source_location.strip() == "":
        # No filtering needed for global scope
        return evidence_list, []
        
    allowed_items = []
    violations = []
    
    for item in evidence_list:
        region = item.get('region_guess')
        if scope_allows(source_location, region):
            allowed_items.append(item)
        else:
            violations.append(item)
    
    # If no items match and we should keep fallback, return best few globally
    if not allowed_items and keep_fallback and violations:
        # Keep up to 2 best items as fallback
        fallback_items = violations[:2]
        return fallback_items, violations[2:] if len(violations) > 2 else []
    
    return allowed_items, violations


def compute_region_weight(
    region_mode: str,
    region_country: str,
    actual_region: Optional[str],
    domain: str
) -> float:
    """
    Compute region-based weight for evidence scoring.
    
    Args:
        region_mode: "global", "country", or "exclude_country"
        region_country: Target country (e.g., "South Africa")
        actual_region: Inferred region from evidence
        domain: Domain name for TLD bonus
        
    Returns:
        Weight multiplier for evidence scoring
    """
    weight = 1.0
    
    if region_mode == "country" and actual_region == region_country:
        weight += 3.0
    elif region_mode == "exclude_country" and actual_region == region_country:
        weight -= 4.0
        
    # TLD bonus for matching domains
    if region_country == "South Africa" and (
        domain.endswith('.za') or domain.endswith('.co.za')
    ):
        weight += 2.0
        
    return max(0.1, weight)  # Minimum weight to avoid zero


def check_domain_fitness(snippet: str, title: str, sector: str = "short-term P&C") -> tuple[bool, str]:
    """
    Check if evidence is from the right business domain.
    
    Args:
        snippet: Text snippet from evidence
        title: Title from evidence  
        sector: Target sector (default: "short-term P&C")
        
    Returns:
        Tuple of (is_wrong_domain, reason)
    """
    if sector.lower() in ["short-term p&c", "short-term insurance", "property casualty"]:
        content = f"{title} {snippet}".lower()
        
        # Health insurance terms that indicate wrong domain
        health_terms = [
            'short-term health insurance', 'stldi', 'aca', 'hhs', 'obamacare',
            'health insurance marketplace', 'medical insurance', 'health coverage',
            'short-term medical', 'temporary health', 'interim health'
        ]
        
        for term in health_terms:
            if term in content:
                return True, f"Evidence discusses health insurance ({term}), not P&C insurance"
                
    return False, ""


def normalize_region_name(region: str) -> str:
    """
    Normalize region names for consistent comparison.
    
    Args:
        region: Raw region name
        
    Returns:
        Normalized region name
    """
    if not region:
        return ""
        
    region = region.strip()
    
    # Common variations
    variations = {
        'za': 'South Africa',
        'sa': 'South Africa', 
        'rsa': 'South Africa',
        'us': 'United States',
        'usa': 'United States',
        'america': 'United States',
        'uk': 'United Kingdom',
        'britain': 'United Kingdom',
        'england': 'United Kingdom'
    }
    
    normalized = variations.get(region.lower(), region)
    return normalized.title() if normalized else region