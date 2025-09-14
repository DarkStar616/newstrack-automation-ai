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
        "test": 2,
        "shallow": 3,
        "fast": 3,  # Keep for backward compatibility
        "deep": 6
    }
    return mode_mapping.get(mode, 3)


def log_search_config():
    """Log current search configuration at startup."""
    mode = get_search_mode()
    provider = get_search_provider()
    recency = get_recency_window()
    max_results = get_max_results_for_mode(mode)
    
    print(f"Search provider={provider}, mode={mode}, window={recency} months, max_results={max_results}")
    
    if mode != "off":
        if provider == "google":
            has_key = bool(os.getenv("GOOGLE_API_KEY"))
            model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
            print(f"Google API key: {'configured' if has_key else 'missing'}, model={model}")
        elif provider == "perplexity":
            has_key = bool(get_perplexity_key())
            print(f"Perplexity API key: {'configured' if has_key else 'missing'}")