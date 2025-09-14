"""
Configuration utilities for Newstrack keyword automation system.
"""
import os


def get_bool(env_var: str, default: bool = False) -> bool:
    """Get boolean value from environment variable."""
    value = os.getenv(env_var, str(default)).lower()
    return value in ("true", "1", "yes", "on")


def get_llm_test_mode() -> bool:
    """Get LLM test mode configuration. Test mode is opt-in only."""
    return get_bool("LLM_TEST_MODE", default=False)


def get_search_test_mode() -> bool:
    """Get search test mode configuration. Test mode is opt-in only."""
    return get_bool("SEARCH_TEST_MODE", default=False)


def get_search_mode() -> str:
    """Get search mode configuration. Defaults to 'shallow' for live operation."""
    return os.getenv("SEARCH_MODE", "shallow")


def get_recency_window() -> int:
    """Get recency window in months for evidence search."""
    return int(os.getenv("RECENCY_WINDOW_MONTHS", "3"))


def get_search_provider() -> str:
    """Get search provider configuration. Defaults to 'google'."""
    return os.getenv("SEARCH_PROVIDER", "google")


def get_cache_ttl_days() -> int:
    """Get cache TTL in days for search results."""
    return int(os.getenv("SEARCH_CACHE_TTL_DAYS", "14"))


def should_bypass_cache() -> bool:
    """Check if cache should be bypassed for search operations."""
    return get_bool("SEARCH_BYPASS_CACHE", default=False)


def get_region_mode() -> str:
    """Get region filtering mode. Defaults to 'global'."""
    return os.getenv("REGION_MODE", "global")


def get_region_country() -> str:
    """Get target country for region filtering. Defaults to 'South Africa'."""
    return os.getenv("REGION_COUNTRY", "South Africa")


def get_query_strategy() -> str:
    """Get query construction strategy. Defaults to 'sector_keyword_region'."""
    return os.getenv("QUERY_STRATEGY", "sector_keyword_region")


def is_region_filter_enabled() -> bool:
    """Check if region filtering is enabled."""
    return get_bool("REGION_FILTER_ENABLED", default=True)


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
    """Log current search configuration at startup with evidence mode info."""
    mode = get_search_mode()
    provider = get_search_provider()
    recency = get_recency_window()
    max_results = get_max_results_for_mode(mode)
    llm_test = get_llm_test_mode()
    search_test = get_search_test_mode()
    cache_ttl = get_cache_ttl_days()
    bypass_cache = should_bypass_cache()
    
    # Region settings
    region_mode = get_region_mode()
    region_country = get_region_country()
    query_strategy = get_query_strategy()
    region_filter = is_region_filter_enabled()
    
    print(f"EvidenceMode: provider={provider} default_mode={mode} llm_test={llm_test} search_test={search_test} cache_ttl={cache_ttl} bypass_cache={bypass_cache}")
    print(f"RegionConfig: mode={region_mode} country={region_country} query_strategy={query_strategy} filter_enabled={region_filter}")
    
    if mode != "off":
        if provider == "google":
            has_key = bool(os.getenv("GOOGLE_API_KEY"))
            model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
            print(f"Google API key: {'configured' if has_key else 'missing'}, model={model}")
        elif provider == "perplexity":
            has_key = bool(get_perplexity_key())
            print(f"Perplexity API key: {'configured' if has_key else 'missing'}")