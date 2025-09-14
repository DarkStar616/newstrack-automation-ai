"""
Evidence ranking and scoring utilities.
Provides weightings for different factors including region, domain, and relevance.
"""
import re
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
from datetime import datetime, timedelta
from src.utils.region import compute_region_weight, check_domain_fitness


def score_evidence_item(
    evidence: Dict[str, Any],
    keyword: str,
    sector: str = "short-term P&C",
    region_mode: str = "global",
    region_country: str = "South Africa"
) -> Dict[str, Any]:
    """
    Score a single evidence item based on multiple factors.
    
    Args:
        evidence: Evidence dictionary with url, title, snippet, etc.
        keyword: The keyword being searched
        sector: Business sector for domain fitness
        region_mode: Region filtering mode  
        region_country: Target country for region scoring
        
    Returns:
        Evidence dict with added 'score' and 'score_breakdown' fields
    """
    score = 0.0
    breakdown = {}
    
    title = evidence.get('title', '')
    snippet = evidence.get('snippet', '')
    url = evidence.get('url', '')
    region = evidence.get('region_guess')
    
    # Parse domain for TLD checks
    domain = ''
    try:
        domain = urlparse(url).netloc.lower()
    except:
        pass
    
    # 1. Region weight
    region_weight = compute_region_weight(region_mode, region_country, region, domain)
    score += region_weight
    breakdown['region'] = region_weight
    
    # 2. Domain fitness (penalty for wrong business domain)
    is_wrong_domain, domain_reason = check_domain_fitness(snippet, title, sector)
    if is_wrong_domain:
        domain_penalty = -3.0
        score += domain_penalty
        breakdown['domain'] = domain_penalty
        breakdown['domain_reason'] = domain_reason
    else:
        breakdown['domain'] = 0.0
    
    # 3. Title relevance (keyword appears in title)
    title_bonus = 0.0
    if keyword.lower() in title.lower():
        title_bonus = 2.0
        score += title_bonus
    breakdown['title_relevance'] = title_bonus
    
    # 4. Sector keywords in title (insurance, underwriting, claims)
    sector_keywords = ['insurance', 'underwriting', 'claims', 'insurer', 'reinsurance', 'coverage']
    sector_bonus = 0.0
    title_lower = title.lower()
    for sector_kw in sector_keywords:
        if sector_kw in title_lower:
            sector_bonus = 1.0
            break
    score += sector_bonus
    breakdown['sector_relevance'] = sector_bonus
    
    # 5. Recency bonus (more recent = higher score)
    recency_bonus = 0.0
    published_date = evidence.get('published_date')
    if published_date:
        try:
            if isinstance(published_date, str):
                pub_date = datetime.fromisoformat(published_date.replace('Z', '+00:00'))
            else:
                pub_date = published_date
                
            days_ago = (datetime.now() - pub_date.replace(tzinfo=None)).days
            
            if days_ago <= 30:
                recency_bonus = 1.5
            elif days_ago <= 90:
                recency_bonus = 1.0
            elif days_ago <= 180:
                recency_bonus = 0.5
            
            score += recency_bonus
        except:
            pass
    breakdown['recency'] = recency_bonus
    
    # 6. Source quality (known financial/insurance publications)
    source_bonus = 0.0
    quality_domains = [
        'bloomberg.com', 'reuters.com', 'ft.com', 'wsj.com',
        'moneyweb.co.za', 'businesslive.co.za', 'fin24.com',
        'insurancejournal.com', 'property-casualty360.com',
        'insurancebusinessmag.com', 'cover.co.za'
    ]
    
    for quality_domain in quality_domains:
        if quality_domain in domain:
            source_bonus = 1.0
            break
    score += source_bonus
    breakdown['source_quality'] = source_bonus
    
    # 7. Content relevance (keyword density and context)
    content_score = _score_content_relevance(keyword, title + ' ' + snippet)
    score += content_score
    breakdown['content_relevance'] = content_score
    
    # Final score (minimum 0.1 to avoid completely zeroing out)
    final_score = max(0.1, score)
    
    # Add scoring info to evidence
    evidence_with_score = evidence.copy()
    evidence_with_score['score'] = round(final_score, 2)
    evidence_with_score['score_breakdown'] = breakdown
    
    return evidence_with_score


def _score_content_relevance(keyword: str, content: str) -> float:
    """Score how relevant the content is to the keyword."""
    if not content or not keyword:
        return 0.0
    
    content_lower = content.lower()
    keyword_lower = keyword.lower()
    
    score = 0.0
    
    # Exact keyword matches
    exact_matches = len(re.findall(re.escape(keyword_lower), content_lower))
    score += exact_matches * 0.5
    
    # Partial matches (for multi-word keywords)
    if ' ' in keyword:
        words = keyword_lower.split()
        word_matches = sum(1 for word in words if word in content_lower)
        score += (word_matches / len(words)) * 0.3
    
    # Related financial terms
    financial_terms = [
        'financial', 'investment', 'fund', 'portfolio', 'asset',
        'liability', 'risk', 'premium', 'policy', 'claim',
        'market', 'regulatory', 'compliance', 'audit'
    ]
    
    related_matches = sum(1 for term in financial_terms if term in content_lower)
    score += min(related_matches * 0.1, 0.5)  # Cap at 0.5
    
    return min(score, 3.0)  # Cap total content score


def rank_evidence_list(
    evidence_list: List[Dict[str, Any]],
    keyword: str,
    sector: str = "short-term P&C", 
    region_mode: str = "global",
    region_country: str = "South Africa",
    max_results: int = 3
) -> List[Dict[str, Any]]:
    """
    Rank and filter evidence list by relevance score.
    
    Args:
        evidence_list: List of evidence items
        keyword: The keyword being searched
        sector: Business sector for domain fitness
        region_mode: Region filtering mode
        region_country: Target country
        max_results: Maximum number of results to return
        
    Returns:
        Ranked and limited evidence list with scores
    """
    # Score each evidence item
    scored_evidence = []
    for evidence in evidence_list:
        scored_item = score_evidence_item(
            evidence, keyword, sector, region_mode, region_country
        )
        scored_evidence.append(scored_item)
    
    # Sort by score (highest first)
    ranked_evidence = sorted(scored_evidence, key=lambda x: x['score'], reverse=True)
    
    # Limit to max results
    return ranked_evidence[:max_results]


def get_score_summary(evidence_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Get summary statistics for evidence scoring.
    
    Args:
        evidence_list: List of scored evidence items
        
    Returns:
        Summary dictionary with stats
    """
    if not evidence_list:
        return {
            'total_items': 0,
            'avg_score': 0.0,
            'score_range': [0.0, 0.0],
            'breakdown_summary': {}
        }
    
    scores = [item.get('score', 0) for item in evidence_list]
    breakdowns = [item.get('score_breakdown', {}) for item in evidence_list]
    
    # Aggregate breakdown categories
    breakdown_summary = {}
    if breakdowns:
        for category in breakdowns[0].keys():
            values = [bd.get(category, 0) for bd in breakdowns if isinstance(bd.get(category), (int, float))]
            if values:
                breakdown_summary[category] = {
                    'avg': round(sum(values) / len(values), 2),
                    'total': round(sum(values), 2)
                }
    
    return {
        'total_items': len(evidence_list),
        'avg_score': round(sum(scores) / len(scores), 2),
        'score_range': [round(min(scores), 2), round(max(scores), 2)],
        'breakdown_summary': breakdown_summary
    }


def filter_low_quality_evidence(
    evidence_list: List[Dict[str, Any]], 
    min_score: float = 0.5
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Filter out low-quality evidence based on score threshold.
    
    Args:
        evidence_list: List of scored evidence items
        min_score: Minimum score threshold
        
    Returns:
        Tuple of (high_quality_items, low_quality_items)
    """
    high_quality = []
    low_quality = []
    
    for item in evidence_list:
        score = item.get('score', 0)
        if score >= min_score:
            high_quality.append(item)
        else:
            low_quality.append(item)
    
    return high_quality, low_quality


def detect_score_anomalies(evidence_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Detect evidence items with unusual scoring patterns.
    
    Args:
        evidence_list: List of scored evidence items
        
    Returns:
        List of anomaly descriptions
    """
    anomalies = []
    
    if len(evidence_list) < 2:
        return anomalies
    
    scores = [item.get('score', 0) for item in evidence_list]
    avg_score = sum(scores) / len(scores)
    
    for i, item in enumerate(evidence_list):
        score = item.get('score', 0)
        breakdown = item.get('score_breakdown', {})
        
        # Very low score anomaly
        if score < 0.3:
            anomalies.append({
                'type': 'very_low_score',
                'item_index': i,
                'score': score,
                'reason': 'Evidence scored unusually low',
                'breakdown': breakdown
            })
        
        # Negative domain score anomaly
        domain_score = breakdown.get('domain', 0)
        if domain_score < -2:
            anomalies.append({
                'type': 'wrong_domain',
                'item_index': i,
                'score': score,
                'reason': breakdown.get('domain_reason', 'Wrong business domain'),
                'breakdown': breakdown
            })
        
        # High score but low relevance anomaly
        content_score = breakdown.get('content_relevance', 0)
        if score > avg_score + 1 and content_score < 0.5:
            anomalies.append({
                'type': 'high_score_low_relevance',
                'item_index': i,
                'score': score,
                'reason': 'High overall score but low content relevance',
                'breakdown': breakdown
            })
    
    return anomalies