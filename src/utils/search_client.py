"""
Search client abstraction layer supporting multiple providers.
Provides unified interface for evidence gathering across providers.
"""
import os
import json
import sqlite3
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
from src.utils.config import (
    get_search_mode, get_search_test_mode, should_bypass_cache, get_cache_ttl_days,
    get_region_mode, get_region_country, get_query_strategy, is_region_filter_enabled
)
from src.utils.region import infer_region, scope_allows, filter_evidence_by_region
from src.utils.ranking import rank_evidence_list


def get_search_provider() -> str:
    """Get the configured search provider."""
    from src.utils.config import get_search_provider as get_configured_provider
    return get_configured_provider().lower()


def search_for_evidence(
    term: str, 
    recency_months: int = 6, 
    max_results: int = 3,
    search_mode: Optional[str] = None,
    sector: str = "short-term P&C",
    source_location: Optional[str] = None,
    region_mode: Optional[str] = None,
    region_country: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Search for evidence using the configured provider with region-aware query construction.
    
    Args:
        term: Search term/keyword
        recency_months: Recency window in months
        max_results: Maximum number of results to return
        search_mode: Optional explicit search mode override
        sector: Business sector for query construction (default: "short-term P&C")
        source_location: Source location rule from Excel (blank | "South Africa" | "!South Africa")
        region_mode: Region filtering mode override
        region_country: Target country override
        
    Returns:
        List of evidence dictionaries with normalized schema:
        [{"provider": str, "url": str, "title": str, "snippet": str, "published_date": str, "region_guess": str}]
    """
    provider = get_search_provider()
    if search_mode is None:
        search_mode = get_search_mode()
    
    # Set defaults for region parameters
    if region_mode is None:
        region_mode = get_region_mode()
    if region_country is None:
        region_country = get_region_country()
    
    # Check for explicit test mode or SEARCH_TEST_MODE environment
    test_mode_active = search_mode == "test" or get_search_test_mode()
    
    # Handle off mode
    if search_mode == "off":
        return []
    
    # Handle test mode with deterministic fakes
    if test_mode_active:
        return _get_test_evidence(term, max_results=2)  # Always 2 for test mode
    
    # Check cache first (unless bypassed)
    cache_key = _get_enhanced_cache_key(provider, term, recency_months, region_mode, region_country, source_location)
    if not should_bypass_cache():
        cached_result = _get_cached_evidence_enhanced(cache_key)
        if cached_result is not None:
            return cached_result[:max_results]
    
    # Build region-aware queries
    queries = _build_region_aware_queries(term, sector, region_mode, region_country)
    
    # Route to appropriate provider for live search with enhanced queries
    all_results = []
    if provider == "google":
        from src.utils.gemini_client import search_with_gemini
        for query in queries:
            query_results = search_with_gemini(query, recency_months, max_results)
            all_results.extend(query_results)
    else:
        # Fallback to existing Perplexity implementation
        from src.utils.perplexity_client import PerplexityClient
        from src.utils.config import get_perplexity_key
        
        perplexity_key = get_perplexity_key()
        if perplexity_key:
            client = PerplexityClient(perplexity_key, search_mode)
            for query in queries:
                query_results = client.search_keyword(query, max_results, recency_months)
                all_results.extend(query_results)
        else:
            all_results = []
    
    # Deduplicate by URL host
    result = _deduplicate_by_host(all_results)
    
    # Add region inference to each result
    for item in result:
        item['region_guess'] = infer_region(
            item.get('url', ''), 
            item.get('snippet', ''), 
            item.get('title', '')
        )
    
    # Apply region filtering based on source_location or region_mode
    if is_region_filter_enabled():
        result = _apply_region_filtering(result, source_location, region_mode, region_country)
    
    # Rank evidence using the new scoring system
    result = rank_evidence_list(
        result, term, sector, region_mode, region_country, max_results
    )
    
    # Cache the result (unless bypassed)
    if not should_bypass_cache() and result:
        _cache_evidence_enhanced(cache_key, result)
    
    return result


def _build_region_aware_queries(term: str, sector: str, region_mode: str, region_country: str) -> List[str]:
    """
    Build region-aware search queries based on the query strategy.
    
    Args:
        term: The keyword to search for
        sector: Business sector for context
        region_mode: "global", "country", or "exclude_country"
        region_country: Target country
        
    Returns:
        List of search query strings
    """
    # Normalize sector for query construction
    if "short-term" in sector.lower() or "p&c" in sector.lower():
        base_sector = "short-term P&C insurance"
    else:
        base_sector = f"{sector} insurance"
    
    queries = []
    
    if region_mode == "global":
        # Global queries - no region constraints
        queries = [
            f"{term} {base_sector}",
            f"{term} {base_sector} latest news",
            f"{term} {base_sector} 2025"
        ]
    
    elif region_mode == "country":
        # Country-specific queries
        country = region_country
        if country == "South Africa":
            queries = [
                f"{term} {base_sector} {country}",
                f"{term} {base_sector} site:(*.co.za OR *.za) OR (\"South Africa\")",
                f"{term} {base_sector} latest news {country}"
            ]
        else:
            queries = [
                f"{term} {base_sector} {country}",
                f"{term} {base_sector} latest news {country}",
                f"{term} {base_sector} 2025 {country}"
            ]
    
    elif region_mode == "exclude_country":
        # Exclude specific country
        country = region_country
        if country == "South Africa":
            queries = [
                f"{term} {base_sector} -\"South Africa\" -site:*.za -site:*.co.za",
                f"{term} {base_sector} latest news -\"South Africa\"",
                f"{term} {base_sector} 2025 -\"South Africa\""
            ]
        else:
            queries = [
                f"{term} {base_sector} -\"{country}\"",
                f"{term} {base_sector} latest news -\"{country}\"",
                f"{term} {base_sector} 2025 -\"{country}\""
            ]
    
    return queries


def _deduplicate_by_host(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate results by URL host to avoid duplicate sources."""
    seen_hosts = set()
    deduplicated = []
    
    for result in results:
        url = result.get('url', '')
        if not url:
            continue
            
        try:
            host = urlparse(url).netloc.lower()
            if host not in seen_hosts:
                seen_hosts.add(host)
                deduplicated.append(result)
        except:
            # Include items with unparseable URLs
            deduplicated.append(result)
    
    return deduplicated


def _apply_region_filtering(
    results: List[Dict[str, Any]], 
    source_location: Optional[str], 
    region_mode: str, 
    region_country: str
) -> List[Dict[str, Any]]:
    """Apply region filtering based on source_location rules or region_mode."""
    
    # Excel source_location takes precedence over region_mode
    if source_location:
        filtered_results, violations = filter_evidence_by_region(results, source_location, keep_fallback=True)
        return filtered_results
    
    # Apply region_mode filtering
    if region_mode == "country":
        # Prefer results from the target country
        country_results = [r for r in results if r.get('region_guess') == region_country]
        if country_results:
            return country_results
        else:
            # Keep best global results as fallback
            return results[:3]
    
    elif region_mode == "exclude_country":
        # Exclude results from the specified country
        filtered = [r for r in results if r.get('region_guess') != region_country]
        return filtered if filtered else results[:2]  # Keep few if all were excluded
    
    # Global mode or no filtering needed
    return results


def _get_enhanced_cache_key(
    provider: str, 
    term: str, 
    recency_months: int, 
    region_mode: str, 
    region_country: str, 
    source_location: Optional[str]
) -> str:
    """Generate cache key that includes region parameters."""
    base_key = f"{provider}:{term}:{recency_months}:{region_mode}:{region_country}"
    if source_location:
        base_key += f":{source_location}"
    return base_key


def _get_cached_evidence_enhanced(cache_key: str) -> Optional[List[Dict[str, Any]]]:
    """Get cached evidence using enhanced cache key."""
    try:
        _ensure_cache_schema()
        db_path = _get_cache_db_path()
        ttl_days = get_cache_ttl_days()
        
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT evidence_json FROM search_cache_enhanced 
                WHERE cache_key = ? AND created_at > datetime('now', '-{} days')
            """.format(ttl_days), (cache_key,))
            
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
    except Exception:
        pass
    
    return None


def _cache_evidence_enhanced(cache_key: str, evidence: List[Dict[str, Any]]):
    """Cache evidence using enhanced cache key."""
    try:
        _ensure_cache_schema()
        db_path = _get_cache_db_path()
        
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO search_cache_enhanced 
                (cache_key, evidence_json, created_at)
                VALUES (?, ?, datetime('now'))
            """, (cache_key, json.dumps(evidence)))
    except Exception:
        pass


def _get_test_evidence(term: str, max_results: int = 2) -> List[Dict[str, Any]]:
    """Generate deterministic test evidence for any term."""
    evidence = []
    for i in range(max_results):
        evidence.append({
            "provider": "test",
            "url": f"https://example.com/news/{term.lower().replace(' ', '-')}-article-{i+1}",
            "title": f"Test Article {i+1}: {term} Industry Update",
            "snippet": f"This is a test evidence snippet about {term}. The article discusses recent developments and trends related to {term} in the current market environment.",
            "published_date": "2025-09-10",
            "region_guess": None
        })
    return evidence


def _get_cache_db_path() -> str:
    """Get path to SQLite cache database."""
    os.makedirs("src/database", exist_ok=True)
    return "src/database/search_cache.sqlite"


def _ensure_cache_schema():
    """Ensure cache database has correct schema with enhanced cache table."""
    db_path = _get_cache_db_path()
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # Create enhanced cache table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS search_cache_enhanced (
                cache_key TEXT PRIMARY KEY,
                evidence_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Keep old table for backward compatibility but create new enhanced one
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS search_cache (
                provider TEXT,
                term TEXT,
                recency_months INTEGER,
                test_mode INTEGER,
                evidence_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (provider, term, recency_months, test_mode)
            )
        """)
        
        conn.commit()


# Legacy cache functions for backward compatibility
def _get_cached_evidence(provider: str, term: str, recency_months: int, test_mode: bool) -> Optional[List[Dict[str, Any]]]:
    """Legacy cached evidence getter."""
    try:
        _ensure_cache_schema()
        db_path = _get_cache_db_path()
        ttl_days = get_cache_ttl_days()
        
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT evidence_json FROM search_cache 
                WHERE provider = ? AND term = ? AND recency_months = ? AND test_mode = ?
                AND created_at > datetime('now', '-{} days')
            """.format(ttl_days), (provider, term, recency_months, int(test_mode)))
            
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
    except Exception:
        pass
    
    return None


def _cache_evidence(provider: str, term: str, recency_months: int, test_mode: bool, evidence: List[Dict[str, Any]]):
    """Legacy evidence caching."""
    try:
        _ensure_cache_schema()
        db_path = _get_cache_db_path()
        
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO search_cache 
                (provider, term, recency_months, test_mode, evidence_json, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
            """, (provider, term, recency_months, int(test_mode), json.dumps(evidence)))
    except Exception:
        pass