"""
Batch processor with token and size control, retry logic, and completeness checking.
"""
import time
import math
from typing import Dict, List, Any, Tuple, Optional
from flask import current_app
from src.utils.llm_client import get_llm_client
from src.utils.guardrails import get_guardrails_engine
from src.utils.audit import get_audit_logger


class BatchProcessor:
    """Handles batch processing with size control and retry logic."""
    
    def __init__(self, default_batch_size: int = 300, max_retries: int = 3):
        self.default_batch_size = default_batch_size
        self.max_retries = max_retries
        self.llm_client = get_llm_client()
        self.guardrails = get_guardrails_engine()
        self.audit_logger = get_audit_logger()
    
    def estimate_token_count(self, text: str) -> int:
        """Rough estimation of token count (4 chars per token average)."""
        return len(text) // 4
    
    def split_keywords_into_batches(self, keywords: List[str], batch_size: int) -> List[List[str]]:
        """Split keywords into batches of specified size."""
        batches = []
        for i in range(0, len(keywords), batch_size):
            batch = keywords[i:i + batch_size]
            batches.append(batch)
        return batches
    
    def process_batch_with_retry(self, 
                               keywords_batch: List[str],
                               sector: str,
                               company: str,
                               date: str,
                               step: str = 'process-all') -> Dict[str, Any]:
        """
        Process a batch of keywords with retry logic and size reduction on failure.
        
        Args:
            keywords_batch: List of keywords to process
            sector: Target sector
            company: Target company (optional)
            date: Current date for processing
            step: Processing step ('categorize', 'expand', 'drop', 'process-all')
            
        Returns:
            Dictionary with processing results and metadata
        """
        start_time = time.time()
        batch_id = self.audit_logger.generate_batch_id()
        
        current_batch = keywords_batch.copy()
        attempt = 1
        
        while attempt <= self.max_retries:
            try:
                current_app.logger.info(f"Processing batch {batch_id}, attempt {attempt}, size: {len(current_batch)}")
                
                # Process the batch
                if step == 'process-all':
                    result = self._process_full_pipeline(current_batch, sector, company, date)
                elif step == 'categorize':
                    result = self._process_categorize_only(current_batch, sector, company)
                elif step == 'expand':
                    # For expand step, we need the categorize result
                    categorize_result = self._process_categorize_only(current_batch, sector, company)
                    result = self._process_expand_only(categorize_result, sector, company)
                elif step == 'drop':
                    # For drop step, we need both categorize and expand results
                    categorize_result = self._process_categorize_only(current_batch, sector, company)
                    expand_result = self._process_expand_only(categorize_result, sector, company)
                    result = self._process_drop_only(expand_result, sector, company, date)
                else:
                    raise ValueError(f"Unknown processing step: {step}")
                
                # Apply guardrails
                guardrails_result = self.guardrails.apply_all_guardrails(
                    current_batch, 
                    result.get('categories', {})
                )
                
                # Check completeness
                is_complete = guardrails_result['guardrails']['completeness_check']['is_complete']
                
                if not is_complete and attempt < self.max_retries:
                    # Completeness check failed, reduce batch size and retry
                    missing = guardrails_result['guardrails']['completeness_check']['missing_keywords']
                    current_app.logger.warning(f"Completeness check failed for batch {batch_id}, attempt {attempt}. Missing: {missing}")
                    
                    # Reduce batch size by half
                    new_size = max(1, len(current_batch) // 2)
                    current_batch = current_batch[:new_size]
                    attempt += 1
                    continue
                
                # Success or final attempt
                timing_ms = int((time.time() - start_time) * 1000)
                
                # Write audit log
                audit_file = self.audit_logger.write_batch_audit(
                    batch_id=batch_id,
                    category=sector,  # Using sector as category for now
                    input_keywords=keywords_batch,
                    final_categories=guardrails_result['categories'],
                    guardrails_result=guardrails_result,
                    timing_ms=timing_ms,
                    step=step
                )
                
                return {
                    'success': True,
                    'batch_id': batch_id,
                    'attempt': attempt,
                    'processed_count': len(current_batch),
                    'original_count': len(keywords_batch),
                    'result': result,
                    'guardrails': guardrails_result,
                    'timing_ms': timing_ms,
                    'audit_file': audit_file,
                    'completeness_check': {
                        'is_complete': is_complete,
                        'missing_keywords': guardrails_result['guardrails']['completeness_check']['missing_keywords']
                    }
                }
                
            except Exception as e:
                current_app.logger.error(f"Batch {batch_id} attempt {attempt} failed: {str(e)}")
                
                if attempt < self.max_retries:
                    # Reduce batch size and retry
                    new_size = max(1, len(current_batch) // 2)
                    current_batch = current_batch[:new_size]
                    attempt += 1
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    # Final failure
                    timing_ms = int((time.time() - start_time) * 1000)
                    return {
                        'success': False,
                        'batch_id': batch_id,
                        'attempt': attempt,
                        'error': str(e),
                        'processed_count': 0,
                        'original_count': len(keywords_batch),
                        'timing_ms': timing_ms
                    }
        
        # Should not reach here
        return {
            'success': False,
            'batch_id': batch_id,
            'error': 'Maximum retries exceeded',
            'processed_count': 0,
            'original_count': len(keywords_batch)
        }
    
    def _process_full_pipeline(self, keywords: List[str], sector: str, company: str, date: str) -> Dict[str, Any]:
        """Process keywords through the full 3-step pipeline."""
        keywords_str = '\n'.join(keywords)
        
        # Step 1: Categorize
        categorize_result = self._process_categorize_only(keywords, sector, company)
        
        # Step 2: Expand
        expand_result = self._process_expand_only(categorize_result, sector, company)
        
        # Step 3: Drop
        drop_result = self._process_drop_only(expand_result, sector, company, date)
        
        return {
            'step1_result': categorize_result,
            'step2_result': expand_result,
            'step3_result': drop_result,
            'categories': drop_result.get('updated', {}),
            'final_result': drop_result
        }
    
    def _process_categorize_only(self, keywords: List[str], sector: str, company: str) -> Dict[str, Any]:
        """Process keywords through categorization step only."""
        keywords_str = '\n'.join(keywords)
        company_or_sector = company if company else sector
        
        prompt = f"""You are a keyword categorization expert. Categorize the following keywords into exactly three categories: industry, company, and regulatory.

SECTOR: {sector}
TARGET ORGANIZATION: {company_or_sector}

KEYWORDS TO CATEGORIZE:
{keywords_str}

INSTRUCTIONS:
1. Sort each keyword into one of these three categories:
   - industry: General industry terms, products, services, market segments
   - company: Specific company names, brands, organizations
   - regulatory: Laws, regulations, compliance terms, government bodies

2. Provide a brief explanation for each category's purpose.

3. Return ONLY valid JSON in this exact format:

{{
    "categories": {{
        "industry": ["keyword1", "keyword2"],
        "company": ["keyword3", "keyword4"],
        "regulatory": ["keyword5", "keyword6"]
    }},
    "explanations": {{
        "industry": "Brief explanation of industry category",
        "company": "Brief explanation of company category", 
        "regulatory": "Brief explanation of regulatory category"
    }}
}}

Do not include any text outside the JSON response."""

        response = self.llm_client.chat_completion([
            {"role": "user", "content": prompt}
        ], temperature=0.1)
        
        return self.llm_client.parse_json_response(response)
    
    def _process_expand_only(self, categorize_result: Dict[str, Any], sector: str, company: str) -> Dict[str, Any]:
        """Process keywords through expansion step only."""
        company_or_sector = company if company else sector
        categories = categorize_result.get('categories', {})
        
        prompt = f"""You are a keyword expansion expert. Expand the existing keyword categories with additional relevant terms for {company_or_sector}.

EXISTING CATEGORIES:
{json.dumps(categories, indent=2)}

INSTRUCTIONS:
1. For each category (industry, company, regulatory), add 3-5 new relevant keywords
2. Keep ALL original keywords and add new ones
3. Focus on terms that would help find relevant news articles
4. Ensure new keywords are appropriate for the category

Return ONLY valid JSON in this exact format:

{{
    "expanded": {{
        "industry": ["all original terms plus new ones"],
        "company": ["all original terms plus new ones"],
        "regulatory": ["all original terms plus new ones"]
    }},
    "notes": "Brief explanation of expansion strategy and rationale"
}}

Do not include any text outside the JSON response."""

        response = self.llm_client.chat_completion([
            {"role": "user", "content": prompt}
        ], temperature=0.1)
        
        return self.llm_client.parse_json_response(response)
    
    def _process_drop_only(self, expand_result: Dict[str, Any], sector: str, company: str, date: str) -> Dict[str, Any]:
        """Process keywords through drop step only."""
        company_or_sector = company if company else sector
        expanded = expand_result.get('expanded', {})
        
        prompt = f"""You are a keyword currency expert. Review the keyword list and remove any terms that may be outdated as of {date} for {company_or_sector}.

CURRENT KEYWORDS:
{json.dumps(expanded, indent=2)}

CURRENT DATE: {date}

INSTRUCTIONS:
1. Identify keywords that may be outdated, obsolete, or no longer relevant
2. Consider company mergers, rebrands, regulatory changes, market exits
3. Keep the majority of keywords - only remove clearly outdated ones
4. Provide specific reasons for each removal

Return ONLY valid JSON in this exact format:

{{
    "updated": {{
        "industry": ["remaining current terms"],
        "company": ["remaining current terms"],
        "regulatory": ["remaining current terms"]
    }},
    "removed": [
        {{"term": "outdated_keyword", "reason": "specific reason for removal"}},
        {{"term": "another_keyword", "reason": "another specific reason"}}
    ],
    "justification": "Brief explanation of removal criteria and date considerations"
}}

Do not include any text outside the JSON response."""

        response = self.llm_client.chat_completion([
            {"role": "user", "content": prompt}
        ], temperature=0.1)
        
        return self.llm_client.parse_json_response(response)


def get_batch_processor(batch_size: int = 300) -> BatchProcessor:
    """Get a batch processor instance."""
    return BatchProcessor(default_batch_size=batch_size)

