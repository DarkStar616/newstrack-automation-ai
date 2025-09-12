"""
Guardrails implementation for keyword processing.
Handles category isolation, deduplication, and completeness checks.
"""
import os
import re
import json
import unicodedata
from typing import Dict, List, Set, Tuple, Any
from flask import current_app


# Module-level cache for guard sets
_guard_cache = None


def load_guards(guards_dir: str = None) -> Dict[str, Set[str]]:
    """Load category guard sets with optional caching and hot reload."""
    global _guard_cache
    
    if guards_dir is None:
        guards_dir = os.getenv("GUARDS_DIR", "guards")
    
    # Check if we should reload
    hot_reload = os.getenv("GUARDS_HOT_RELOAD", "false").lower() == "true"
    
    if not hot_reload and _guard_cache is not None:
        return _guard_cache
    
    guards = {}
    categories = ['industry', 'company', 'regulatory']
    
    for category in categories:
        guard_file = os.path.join(guards_dir, f'{category}.txt')
        keywords = set()
        
        if os.path.exists(guard_file):
            try:
                with open(guard_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip().lower()  # Normalize: strip, lower
                        if line and not line.startswith('#'):  # Drop blanks and comments
                            keywords.add(line)
            except Exception as e:
                if current_app:
                    current_app.logger.warning(f"Failed to load guard file {guard_file}: {e}")
        
        guards[category] = keywords
    
    _guard_cache = guards
    return guards


def enforce_isolation(categories: Dict[str, List[str]]) -> Tuple[Dict[str, List[str]], List[str]]:
    """Enforce cross-category isolation by removing leaked terms.
    
    Args:
        categories: Dict with industry/company/regulatory keyword lists
        
    Returns:
        Tuple of (cleaned_categories, leaks_blocked_list)
    """
    guard_sets = load_guards()
    cleaned = {k: [] for k in categories.keys()}
    leaks_blocked = []
    
    for category, keywords in categories.items():
        current_guard_set = guard_sets.get(category, set())
        
        for keyword in keywords:
            normalized = keyword.lower().strip()
            is_leaked = False
            
            # Check if this keyword appears in ANY OTHER guard set
            for other_category, other_guard_set in guard_sets.items():
                if other_category != category and normalized in other_guard_set:
                    # This is a leak - keyword belongs in other_category but is in current category
                    leaks_blocked.append(keyword)
                    is_leaked = True
                    break
            
            if not is_leaked:
                cleaned[category].append(keyword)
    
    return cleaned, leaks_blocked


class GuardrailsEngine:
    """Engine for applying guardrails to keyword processing results."""
    
    def __init__(self):
        self.guards_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'guards')
        self.canonical_mappings = self._load_canonical_mappings()
        self.category_guards = self._load_category_guards()
        
    def _load_category_guards(self) -> Dict[str, Set[str]]:
        """Load category guard keywords from files."""
        guards = {}
        categories = ['industry', 'company', 'regulatory']
        
        for category in categories:
            guard_file = os.path.join(self.guards_dir, f'{category}.txt')
            keywords = set()
            
            if os.path.exists(guard_file):
                try:
                    with open(guard_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#'):
                                keywords.add(self._normalize_keyword(line))
                except Exception as e:
                    current_app.logger.warning(f"Failed to load guard file {guard_file}: {e}")
            
            guards[category] = keywords
            
        return guards
    
    def _load_canonical_mappings(self) -> Dict[str, str]:
        """Load canonical keyword mappings."""
        # For now, return a simple mapping. In production, this could be loaded from a file.
        return {
            'auto insurance': 'car insurance',
            'vehicle insurance': 'car insurance',
            'motor insurance': 'car insurance',
            'artificial intelligence': 'ai',
            'machine learning': 'ml',
        }
    
    def _normalize_keyword(self, keyword: str) -> str:
        """Normalize a keyword for comparison."""
        # Convert to lowercase
        normalized = keyword.lower().strip()
        
        # Unicode normalization
        normalized = unicodedata.normalize('NFKD', normalized)
        
        # Remove extra whitespace
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # Apply canonical mapping if exists
        if normalized in self.canonical_mappings:
            normalized = self.canonical_mappings[normalized]
            
        return normalized
    
    def _simple_singularize(self, word: str) -> str:
        """Simple singularization for deduplication."""
        word = word.lower()
        if word.endswith('ies'):
            return word[:-3] + 'y'
        elif word.endswith('es') and len(word) > 3:
            return word[:-2]
        elif word.endswith('s') and len(word) > 2:
            return word[:-1]
        return word
    
    def apply_category_isolation(self, categories: Dict[str, List[str]]) -> Tuple[Dict[str, List[str]], List[str]]:
        """
        Apply category isolation guardrails using the module-level enforce_isolation function.
        
        Returns:
            Tuple of (cleaned_categories, leaks_blocked)
        """
        return enforce_isolation(categories)
    
    def _find_correct_category(self, normalized_keyword: str) -> str:
        """Find the correct category for a keyword based on guards."""
        for category, guard_keywords in self.category_guards.items():
            if normalized_keyword in guard_keywords:
                return category
            
            # Check for partial matches for company names
            if category == 'company':
                for guard_keyword in guard_keywords:
                    if guard_keyword in normalized_keyword or normalized_keyword in guard_keyword:
                        return category
        
        return None
    
    def apply_deduplication(self, categories: Dict[str, List[str]]) -> Tuple[Dict[str, List[str]], List[str]]:
        """
        Apply deduplication across and within categories.
        
        Returns:
            Tuple of (deduplicated_categories, duplicates_dropped)
        """
        global_seen = set()
        deduplicated = {cat: [] for cat in categories.keys()}
        duplicates_dropped = []
        
        for category, keywords in categories.items():
            category_seen = set()
            
            for keyword in keywords:
                normalized = self._normalize_keyword(keyword)
                singular = self._simple_singularize(normalized)
                
                # Check for duplicates (exact, normalized, or singular form)
                if (normalized in global_seen or 
                    singular in global_seen or 
                    normalized in category_seen):
                    duplicates_dropped.append(keyword)
                    current_app.logger.info(f"Duplicate dropped: {keyword}")
                    continue
                
                # Add to seen sets
                global_seen.add(normalized)
                global_seen.add(singular)
                category_seen.add(normalized)
                
                deduplicated[category].append(keyword)
        
        return deduplicated, duplicates_dropped
    
    def apply_completeness_check(self, 
                                input_keywords: List[str], 
                                output_categories: Dict[str, List[str]]) -> Tuple[bool, List[str]]:
        """
        Check that all input keywords are accounted for in output.
        
        Returns:
            Tuple of (is_complete, missing_keywords)
        """
        # Normalize input keywords
        input_normalized = {self._normalize_keyword(kw): kw for kw in input_keywords}
        
        # Collect all output keywords
        output_keywords = []
        for category_keywords in output_categories.values():
            output_keywords.extend(category_keywords)
        
        # Normalize output keywords
        output_normalized = {self._normalize_keyword(kw) for kw in output_keywords}
        
        # Find missing keywords
        missing = []
        for norm_input, original_input in input_normalized.items():
            if norm_input not in output_normalized:
                missing.append(original_input)
        
        is_complete = len(missing) == 0
        
        if not is_complete:
            current_app.logger.warning(f"Completeness check failed. Missing keywords: {missing}")
        
        return is_complete, missing
    
    def apply_all_guardrails(self, 
                           input_keywords: List[str],
                           categories: Dict[str, List[str]]) -> Dict[str, Any]:
        """
        Apply all guardrails and return comprehensive results.
        
        Returns:
            Dictionary with processed categories and guardrail results
        """
        # Apply category isolation
        isolated_categories, leaks_blocked = self.apply_category_isolation(categories)
        
        # Apply deduplication
        deduplicated_categories, duplicates_dropped = self.apply_deduplication(isolated_categories)
        
        # Apply completeness check
        is_complete, missing_keywords = self.apply_completeness_check(input_keywords, deduplicated_categories)
        
        # Calculate counts
        input_total = len(input_keywords)
        output_total = sum(len(keywords) for keywords in deduplicated_categories.values())
        
        return {
            'categories': deduplicated_categories,
            'guardrails': {
                'leaks_blocked': leaks_blocked,
                'duplicates_dropped': duplicates_dropped,
                'completeness_check': {
                    'is_complete': is_complete,
                    'missing_keywords': missing_keywords
                },
                'counts': {
                    'input_total': input_total,
                    'output_accounted': output_total,
                    'leaks_blocked': len(leaks_blocked),
                    'duplicates_dropped': len(duplicates_dropped)
                }
            }
        }


def get_guardrails_engine() -> GuardrailsEngine:
    """Get a guardrails engine instance."""
    return GuardrailsEngine()

