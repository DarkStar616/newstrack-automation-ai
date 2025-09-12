"""
Perplexity Sonar API client for evidence-based keyword validation.
"""
import os
import json
import httpx
from typing import List, Dict, Any
from datetime import datetime, timedelta


class PerplexityClient:
    """Client for Perplexity Sonar API to gather evidence for keyword relevance."""
    
    def __init__(self, api_key: str, mode: str = "fast"):
        """
        Initialize Perplexity client.
        
        Args:
            api_key: Perplexity API key
            mode: Search mode - "off", "fast", or "deep"
        """
        self.api_key = api_key
        self.mode = mode
        self.base_url = "https://api.perplexity.ai/chat/completions"
    
    def search_keyword(self, term: str, max_results: int = 3, recency_months: int = 6) -> List[Dict[str, Any]]:
        """
        Call Perplexity Sonar API for live evidence about a keyword.
        
        Args:
            term: Keyword to search for
            max_results: Maximum number of results to return
            recency_months: How many months back to search
            
        Returns:
            List of Evidence dicts:
            {
              "provider": "perplexity",
              "url": "https://example.com",
              "title": "Article Title", 
              "snippet": "Short excerpt...",
              "published_date": "2025-07-03",
              "first_seen_date": "2025-07-05"
            }
        """
        # Test mode - return deterministic stub data
        if os.getenv("SEARCH_TEST_MODE", "false").lower() == "true":
            return self._get_test_evidence(term, max_results)
        
        # Skip if no API key or mode is off
        if not self.api_key or self.mode == "off":
            return []
        
        try:
            return self._call_perplexity_api(term, max_results, recency_months)
        except Exception as e:
            print(f"Perplexity API error for term '{term}': {e}")
            return []
    
    def _get_test_evidence(self, term: str, max_results: int) -> List[Dict[str, Any]]:
        """Return deterministic test evidence for testing mode."""
        base_evidence = [
            {
                "provider": "perplexity",
                "url": f"https://example.com/news/{term.lower().replace(' ', '-')}-article-1",
                "title": f"Recent developments in {term}",
                "snippet": f"This article discusses recent trends and developments related to {term} in the industry.",
                "published_date": "2025-07-15",
                "first_seen_date": "2025-07-16"
            },
            {
                "provider": "perplexity", 
                "url": f"https://example.com/analysis/{term.lower().replace(' ', '-')}-analysis",
                "title": f"{term} market analysis",
                "snippet": f"Comprehensive analysis of {term} market conditions and regulatory updates.",
                "published_date": "2025-08-02",
                "first_seen_date": "2025-08-03"
            }
        ]
        return base_evidence[:max_results]
    
    def _call_perplexity_api(self, term: str, max_results: int, recency_months: int) -> List[Dict[str, Any]]:
        """Make actual API call to Perplexity Sonar."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Calculate date cutoff
        cutoff_date = datetime.now() - timedelta(days=recency_months * 30)
        cutoff_str = cutoff_date.strftime("%Y-%m-%d")
        
        prompt = (
            f"Give me up to {max_results} recent web references within last {recency_months} months "
            f"about '{term}', return JSON with url, title, snippet, date. Focus on news, regulatory updates, "
            f"and business developments since {cutoff_str}."
        )
        
        payload = {
            "model": "sonar-small-online",  # Shallow, cost-effective
            "messages": [
                {
                    "role": "system",
                    "content": "You are a research assistant. Return only valid JSON with an array of articles."
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            "max_tokens": 1000,
            "temperature": 0.1
        }
        
        with httpx.Client(timeout=30.0) as client:
            response = client.post(self.base_url, headers=headers, json=payload)
            response.raise_for_status()
            
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # Parse JSON response from Perplexity
            try:
                articles = json.loads(content)
                if not isinstance(articles, list):
                    articles = articles.get("articles", []) if isinstance(articles, dict) else []
                
                evidence = []
                for article in articles[:max_results]:
                    evidence.append({
                        "provider": "perplexity",
                        "url": article.get("url", ""),
                        "title": article.get("title", ""),
                        "snippet": article.get("snippet", "")[:200],  # Limit snippet length
                        "published_date": article.get("date", article.get("published_date", "")),
                        "first_seen_date": datetime.now().strftime("%Y-%m-%d")
                    })
                
                return evidence
                
            except json.JSONDecodeError:
                print(f"Failed to parse Perplexity response for term '{term}'")
                return []