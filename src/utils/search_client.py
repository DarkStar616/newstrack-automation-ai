"""
Search client abstraction layer supporting multiple providers.
Provides unified interface for evidence gathering across providers.
"""
import os
import json
import sqlite3
from typing import List, Dict, Any, Optional
from src.utils.config import get_search_mode, get_search_test_mode, should_bypass_cache, get_cache_ttl_days


def get_search_provider() -> str:
    """Get the configured search provider."""
    from src.utils.config import get_search_provider as get_configured_provider
    return get_configured_provider().lower()


def search_for_evidence(
    term: str, 
    recency_months: int = 6, 
    max_results: int = 3,
    search_mode: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Search for evidence using the configured provider.
    
    Args:
        term: Search term/keyword
        recency_months: Recency window in months
        max_results: Maximum number of results to return
        search_mode: Optional explicit search mode override
        
    Returns:
        List of evidence dictionaries with normalized schema:
        [{"provider": str, "url": str, "title": str, "snippet": str, "published_date": str}]
    """
    provider = get_search_provider()
    if search_mode is None:
        search_mode = get_search_mode()
    
    # Check for explicit test mode or SEARCH_TEST_MODE environment
    test_mode_active = search_mode == "test" or get_search_test_mode()
    
    # Handle off mode
    if search_mode == "off":
        return []
    
    # Handle test mode with deterministic fakes
    if test_mode_active:
        return _get_test_evidence(term, max_results=2)  # Always 2 for test mode
    
    # Check cache first (unless bypassed)
    if not should_bypass_cache():
        cached_result = _get_cached_evidence(provider, term, recency_months, test_mode_active)
        if cached_result is not None:
            return cached_result
    
    # Route to appropriate provider for live search
    if provider == "google":
        from src.utils.gemini_client import search_with_gemini
        result = search_with_gemini(term, recency_months, max_results)
    else:
        # Fallback to existing Perplexity implementation
        from src.utils.perplexity_client import PerplexityClient
        from src.utils.config import get_perplexity_key
        
        perplexity_key = get_perplexity_key()
        if perplexity_key:
            client = PerplexityClient(perplexity_key, search_mode)
            result = client.search_keyword(term, max_results, recency_months)
        else:
            result = []
    
    # Cache the result (unless bypassed)
    if not should_bypass_cache() and result:
        _cache_evidence(provider, term, recency_months, test_mode_active, result)
    
    return result


def _get_test_evidence(term: str, max_results: int = 2) -> List[Dict[str, Any]]:
    """Generate deterministic test evidence for any term."""
    evidence = []
    for i in range(max_results):
        evidence.append({
            "provider": "test",
            "url": f"https://example.com/news/{term.lower().replace(' ', '-')}-article-{i+1}",
            "title": f"Test Article {i+1}: {term} Industry Update",
            "snippet": f"This is a test evidence snippet about {term}. The article discusses recent developments and trends related to {term} in the current market environment.",
            "published_date": "2025-09-10"
        })
    return evidence


def _get_cache_db_path() -> str:
    """Get path to SQLite cache database."""
    import os
    os.makedirs("src/database", exist_ok=True)
    return "src/database/search_cache.sqlite"


def _ensure_cache_schema():
    """Ensure cache database has correct schema with migration support."""
    db_path = _get_cache_db_path()
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='search_cache'
        """)
        
        if not cursor.fetchone():
            # Create new table with full schema
            cursor.execute("""
                CREATE TABLE search_cache (
                    provider TEXT,
                    term TEXT,
                    recency_months INTEGER,
                    test_mode INTEGER,
                    evidence_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (provider, term, recency_months, test_mode)
                )
            """)
            print("Created search cache table with new schema")
        else:
            # Check if we need to migrate (add provider and test_mode columns)
            cursor.execute("PRAGMA table_info(search_cache)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'provider' not in columns or 'test_mode' not in columns:
                print("Migrating search cache: dropping old table and recreating")
                cursor.execute("DROP TABLE search_cache")
                cursor.execute("""
                    CREATE TABLE search_cache (
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


def _get_cached_evidence(provider: str, term: str, recency_months: int, test_mode: bool) -> Optional[List[Dict[str, Any]]]:
    """Get cached evidence if available and not expired."""
    _ensure_cache_schema()
    
    db_path = _get_cache_db_path()
    ttl_days = get_cache_ttl_days()
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT evidence_json FROM search_cache 
            WHERE provider = ? AND term = ? AND recency_months = ? AND test_mode = ?
            AND datetime(created_at, '+{} days') > datetime('now')
        """.format(ttl_days), (provider, term.lower(), recency_months, int(test_mode)))
        
        result = cursor.fetchone()
        if result:
            try:
                return json.loads(result[0])
            except json.JSONDecodeError:
                return None
    
    return None


def _cache_evidence(provider: str, term: str, recency_months: int, test_mode: bool, evidence: List[Dict[str, Any]]):
    """Cache evidence results."""
    _ensure_cache_schema()
    
    db_path = _get_cache_db_path()
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO search_cache 
            (provider, term, recency_months, test_mode, evidence_json, created_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (provider, term.lower(), recency_months, int(test_mode), json.dumps(evidence)))
        
        conn.commit()