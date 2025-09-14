"""
Search client abstraction layer supporting multiple providers.
Provides unified interface for evidence gathering across providers.
"""
import os
from typing import List, Dict, Any, Optional
from src.utils.config import get_search_mode


def get_search_provider() -> str:
    """Get the configured search provider."""
    return os.getenv("SEARCH_PROVIDER", "perplexity").lower()


def search_for_evidence(
    term: str, 
    recency_months: int = 6, 
    max_results: int = 3
) -> List[Dict[str, Any]]:
    """
    Search for evidence using the configured provider.
    
    Args:
        term: Search term/keyword
        recency_months: Recency window in months
        max_results: Maximum number of results to return
        
    Returns:
        List of evidence dictionaries with normalized schema:
        [{"provider": str, "url": str, "title": str, "snippet": str, "published_date": str}]
    """
    provider = get_search_provider()
    search_mode = get_search_mode()
    
    # Handle off mode
    if search_mode == "off":
        return []
    
    # Handle test mode with deterministic fakes
    if search_mode == "test":
        return _get_test_evidence(term, max_results=2)  # Always 2 for test mode
    
    # Route to appropriate provider
    if provider == "google":
        from src.utils.gemini_client import search_with_gemini
        return search_with_gemini(term, recency_months, max_results)
    else:
        # Fallback to existing Perplexity implementation
        from src.utils.perplexity_client import PerplexityClient
        from src.utils.config import get_perplexity_key
        
        perplexity_key = get_perplexity_key()
        if perplexity_key:
            client = PerplexityClient(perplexity_key, search_mode)
            return client.search_keyword(term, max_results, recency_months)
        return []


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