"""
Configuration utilities for Newstrack keyword automation system.
"""
import os


def get_search_mode() -> str:
    """Get search mode configuration. Returns 'off', 'fast', or 'deep'."""
    return os.getenv("SEARCH_MODE", "off")


def get_recency_window() -> int:
    """Get recency window in months for evidence search."""
    return int(os.getenv("RECENCY_WINDOW_MONTHS", "6"))


def get_search_provider() -> str:
    """Get search provider configuration."""
    return os.getenv("SEARCH_PROVIDER", "perplexity")


def get_perplexity_key() -> str:
    """Get Perplexity API key from environment."""
    return os.getenv("PERPLEXITY_API_KEY", "")


def get_max_results_for_mode(mode: str) -> int:
    """Get maximum results based on search mode."""
    mode_mapping = {
        "off": 0,
        "fast": 3,
        "deep": 6
    }
    return mode_mapping.get(mode, 3)


def log_search_config():
    """Log current search configuration at startup."""
    mode = get_search_mode()
    provider = get_search_provider()
    recency = get_recency_window()
    max_results = get_max_results_for_mode(mode)
    
    print(f"Search Config: mode={mode}, provider={provider}, recency={recency}mo, max_results={max_results}")
    
    if mode != "off" and provider == "perplexity":
        has_key = bool(get_perplexity_key())
        print(f"Perplexity API key: {'configured' if has_key else 'missing'}")