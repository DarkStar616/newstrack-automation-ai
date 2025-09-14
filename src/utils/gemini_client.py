"""
Google Gemini client for evidence gathering using google_search_retrieval.
Provides search functionality through Gemini 1.5 Flash with search tools.
"""
import os
import json
import time
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dateutil.relativedelta import relativedelta


def get_google_api_key() -> Optional[str]:
    """Get Google API key from environment."""
    return os.getenv("GOOGLE_API_KEY")


def get_gemini_model() -> str:
    """Get Gemini model name from environment."""
    return os.getenv("GEMINI_MODEL", "gemini-1.5-flash")


def search_with_gemini(term: str, recency_months: int, max_results: int) -> List[Dict[str, Any]]:
    """
    Search for evidence using Gemini 1.5 Flash with google_search_retrieval.
    
    Args:
        term: Search term/keyword
        recency_months: Recency window in months
        max_results: Maximum number of results to return
        
    Returns:
        List of evidence dictionaries with normalized schema
    """
    # Check cache first
    cached_results = _get_cached_results(term, recency_months)
    if cached_results:
        return cached_results[:max_results]
    
    try:
        import google.generativeai as genai  # type: ignore
        
        api_key = get_google_api_key()
        if not api_key:
            return []
        
        genai.configure(api_key=api_key)
        
        # Create model with google_search_retrieval tool
        model = genai.GenerativeModel(
            model_name=get_gemini_model(),
            tools=[{"google_search_retrieval": {}}]
        )
        
        # Build search prompt with recency bias
        cutoff_date = datetime.now() - relativedelta(months=recency_months)
        cutoff_str = cutoff_date.strftime("%Y-%m-%d")
        
        prompt = f"""Search for recent news articles about "{term}" published after {cutoff_str} (last {recency_months} months).

Return exactly {max_results} relevant news articles in strict JSON format with no additional text:

{{
  "articles": [
    {{
      "url": "full article URL",
      "title": "article title", 
      "snippet": "brief description or excerpt",
      "published_date": "YYYY-MM-DD"
    }}
  ]
}}

Focus on recent, credible news sources. Each article should be directly relevant to "{term}". Return only the JSON, no other text."""
        
        # Generate response with timeout (can't use JSON mode with search grounding)
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.1
            )
        )
        
        # Parse response
        evidence = _parse_gemini_response(response.text, term)
        
        # Cache results
        _cache_results(term, recency_months, evidence)
        
        return evidence[:max_results]
        
    except Exception as e:
        # Log error but don't fail the pipeline
        print(f"Gemini search error for '{term}': {e}")
        return []


def _parse_gemini_response(response_text: str, term: str) -> List[Dict[str, Any]]:
    """Parse Gemini response and normalize to evidence schema."""
    try:
        # First try to find JSON in the response text
        import re
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            
            evidence = []
            articles = data.get("articles", [])
            
            for article in articles:
                if isinstance(article, dict):
                    evidence.append({
                        "provider": "google",
                        "url": article.get("url", ""),
                        "title": article.get("title", ""),
                        "snippet": article.get("snippet", ""),
                        "published_date": article.get("published_date", "2025-09-12")
                    })
            
            return evidence
        else:
            # Fallback: parse from text format
            return _parse_text_response(response_text, term)
            
    except (json.JSONDecodeError, KeyError) as e:
        # Fallback: parse from text format
        return _parse_text_response(response_text, term)


def _parse_text_response(response_text: str, term: str) -> List[Dict[str, Any]]:
    """Parse text response from Gemini and extract article information."""
    evidence = []
    
    # Simple text parsing for fallback - extract URLs, titles, snippets
    import re
    
    # Look for URL patterns
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    urls = re.findall(url_pattern, response_text)
    
    # Create evidence from found URLs (basic fallback)
    for i, url in enumerate(urls[:3]):  # Limit to 3 results
        evidence.append({
            "provider": "google",
            "url": url,
            "title": f"Search result {i+1} for {term}",
            "snippet": f"Google search result about {term} from recent news coverage.",
            "published_date": "2025-09-12"
        })
    
    return evidence


def _get_cache_db_path() -> str:
    """Get path to SQLite cache database."""
    cache_dir = "results"
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, "cache.sqlite")


def _init_cache_db():
    """Initialize cache database with provider column."""
    db_path = _get_cache_db_path()
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS search_cache (
                term TEXT,
                recency_months INTEGER,
                provider TEXT DEFAULT 'google',
                results TEXT,
                created_at TIMESTAMP,
                PRIMARY KEY (term, recency_months, provider)
            )
        """)
        
        # Add provider column if it doesn't exist (for backward compatibility)
        try:
            conn.execute("ALTER TABLE search_cache ADD COLUMN provider TEXT DEFAULT 'google'")
        except sqlite3.OperationalError:
            pass  # Column already exists


def _get_cached_results(term: str, recency_months: int) -> Optional[List[Dict[str, Any]]]:
    """Get cached search results if not expired (14-day TTL)."""
    try:
        _init_cache_db()
        db_path = _get_cache_db_path()
        
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute("""
                SELECT results FROM search_cache 
                WHERE term = ? AND recency_months = ? AND provider = 'google'
                AND created_at > datetime('now', '-14 days')
            """, (term, recency_months))
            
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
                
    except Exception as e:
        print(f"Cache read error: {e}")
    
    return None


def _cache_results(term: str, recency_months: int, results: List[Dict[str, Any]]):
    """Cache search results with 14-day TTL."""
    try:
        _init_cache_db()
        db_path = _get_cache_db_path()
        
        with sqlite3.connect(db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO search_cache 
                (term, recency_months, provider, results, created_at)
                VALUES (?, ?, 'google', ?, datetime('now'))
            """, (term, recency_months, json.dumps(results)))
            
    except Exception as e:
        print(f"Cache write error: {e}")