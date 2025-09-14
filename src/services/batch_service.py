"""
Batch processing service for auto-batching CSV uploads with queue management,
progress tracking, and resilient processing with retry logic.
"""
import json
import time
import logging
import threading
import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.services.newstrack_service import do_categorize, do_expand, do_drop
from src.utils.audit import get_audit_logger
from src.utils.config import (
    get_search_mode, get_recency_window, get_search_provider, 
    get_llm_test_mode, get_search_test_mode, should_bypass_cache,
    get_max_results_for_mode
)


class BatchStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress" 
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BatchResult:
    batch_id: str
    status: BatchStatus
    keywords_processed: int
    success: bool
    timing_ms: Optional[int] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result_data: Optional[Dict[str, Any]] = None


@dataclass
class BatchGroup:
    group_id: str
    total_batches: int
    total_keywords: int
    created_at: str
    status: str
    batches: List[Dict[str, Any]]
    completed_batches: int = 0
    failed_batches: int = 0
    in_progress_batches: int = 0


class BatchService:
    """Service for managing batch processing of keywords with auto-batching."""
    
    def __init__(self, max_concurrent_batches: int = 3, results_dir: str = "results"):
        self.max_concurrent_batches = max_concurrent_batches
        self.results_dir = results_dir
        self.batch_groups: Dict[str, BatchGroup] = {}
        self.batch_results: Dict[str, BatchResult] = {}
        self.executor = ThreadPoolExecutor(max_workers=max_concurrent_batches)
        self.lock = threading.Lock()
        
        # Ensure results directory exists
        os.makedirs(results_dir, exist_ok=True)
        
        # Load existing batch data if any
        self._load_persistent_data()
    
    
    def create_batch_group(self, group_id: str, batches: List[Dict[str, Any]], 
                          total_keywords: int) -> BatchGroup:
        """Create a new batch group and initialize tracking."""
        batch_group = BatchGroup(
            group_id=group_id,
            total_batches=len(batches),
            total_keywords=total_keywords,
            created_at=datetime.now().isoformat(),
            status="created",
            batches=batches
        )
        
        with self.lock:
            self.batch_groups[group_id] = batch_group
            
            # Initialize batch results
            for batch in batches:
                batch_result = BatchResult(
                    batch_id=batch['batch_id'],
                    status=BatchStatus.PENDING,
                    keywords_processed=0,
                    success=False
                )
                self.batch_results[batch['batch_id']] = batch_result
        
        self._save_persistent_data()
        logging.info(f"Created batch group {group_id} with {len(batches)} batches")
        return batch_group
    
    
    def start_batch_processing(self, group_id: str, sector: str, 
                             processing_config: Dict[str, Any]) -> bool:
        """Start processing all batches in a group with controlled concurrency."""
        if group_id not in self.batch_groups:
            raise ValueError(f"Batch group {group_id} not found")
        
        batch_group = self.batch_groups[group_id]
        
        with self.lock:
            if batch_group.status == "processing":
                return False  # Already processing
            batch_group.status = "processing"
        
        # Submit batches for processing with concurrency control
        futures = []
        for batch in batch_group.batches:
            future = self.executor.submit(
                self._process_single_batch,
                batch['batch_id'],
                batch['keywords'],
                sector,
                processing_config
            )
            futures.append(future)
            
            # Limit concurrent processing
            if len(futures) >= self.max_concurrent_batches:
                # Wait for at least one to complete
                as_completed(futures, timeout=1)
        
        # Start monitoring thread
        monitor_thread = threading.Thread(
            target=self._monitor_batch_group,
            args=(group_id, futures)
        )
        monitor_thread.daemon = True
        monitor_thread.start()
        
        logging.info(f"Started processing batch group {group_id}")
        return True
    
    
    def _process_single_batch(self, batch_id: str, keywords: List[Dict[str, Any]], 
                            sector: str, processing_config: Dict[str, Any]) -> BatchResult:
        """Process a single batch of keywords with live processing."""
        start_time = time.time()
        
        # Update status to in progress
        with self.lock:
            if batch_id in self.batch_results:
                self.batch_results[batch_id].status = BatchStatus.IN_PROGRESS
                self.batch_results[batch_id].started_at = datetime.now().isoformat()
        
        try:
            logging.info(f"Processing batch {batch_id} with {len(keywords)} keywords")
            
            # Extract keyword strings and source locations
            keyword_strings = []
            source_locations = {}
            
            for kw in keywords:
                keyword_str = kw['keyword']
                keyword_strings.append(keyword_str)
                
                # Build region config
                region_config = {
                    'region_mode': kw.get('region_mode', 'GLOBAL'),
                    'country': kw.get('country', None)
                }
                source_locations[keyword_str] = region_config
            
            # Process with the three-step pipeline (LIVE mode)
            result = self._run_keyword_pipeline(
                sector=sector,
                keywords=keyword_strings,
                source_locations=source_locations,
                processing_config=processing_config
            )
            
            if not result.get('success', False):
                raise Exception(f"Pipeline processing failed: {result.get('error', 'Unknown error')}")
            
            # Calculate timing
            timing_ms = int((time.time() - start_time) * 1000)
            
            # Update result
            batch_result = BatchResult(
                batch_id=batch_id,
                status=BatchStatus.COMPLETED,
                keywords_processed=len(keywords),
                success=True,
                timing_ms=timing_ms,
                completed_at=datetime.now().isoformat(),
                result_data=result
            )
            
            # Save batch result to file
            self._save_batch_result(batch_result)
            
            with self.lock:
                self.batch_results[batch_id] = batch_result
            
            logging.info(f"Completed batch {batch_id} in {timing_ms}ms")
            return batch_result
            
        except Exception as e:
            # Handle batch failure
            error_msg = str(e)
            timing_ms = int((time.time() - start_time) * 1000)
            
            batch_result = BatchResult(
                batch_id=batch_id,
                status=BatchStatus.FAILED,
                keywords_processed=0,
                success=False,
                timing_ms=timing_ms,
                error=error_msg,
                completed_at=datetime.now().isoformat()
            )
            
            with self.lock:
                self.batch_results[batch_id] = batch_result
            
            logging.error(f"Batch {batch_id} failed: {error_msg}")
            return batch_result
    
    
    def _run_keyword_pipeline(self, sector: str, keywords: List[str], 
                            source_locations: Dict[str, Dict], 
                            processing_config: Dict[str, Any]) -> Dict[str, Any]:
        """Run the three-step keyword processing pipeline with live evidence gathering."""
        current_date = processing_config.get('current_date', datetime.now().strftime('%Y-%m-%d'))
        search_mode = processing_config.get('search_mode', 'shallow')
        
        # Build request data
        request_data = {
            'sector': sector,
            'keywords': keywords,
            'current_date': current_date,
            'search_mode': search_mode,
            'source_locations': source_locations
        }
        
        # Step 1: Categorize
        step1_result = do_categorize(request_data)
        if not step1_result.get('success', False):
            raise Exception(f"Step 1 (Categorize) failed: {step1_result.get('error', 'Unknown error')}")
        
        # Step 2: Expand
        step2_result = do_expand(step1_result)
        if not step2_result.get('success', False):
            raise Exception(f"Step 2 (Expand) failed: {step2_result.get('error', 'Unknown error')}")
        
        # Step 3: Drop (with live evidence gathering)
        final_result = do_drop(step2_result)
        if not final_result.get('success', False):
            raise Exception(f"Step 3 (Drop) failed: {final_result.get('error', 'Unknown error')}")
        
        return final_result
    
    
    def _monitor_batch_group(self, group_id: str, futures: List):
        """Monitor batch group progress and update status."""
        try:
            # Wait for all futures to complete
            for future in as_completed(futures):
                try:
                    result = future.result()
                    self._update_group_progress(group_id)
                except Exception as e:
                    logging.error(f"Batch future failed: {e}")
                    self._update_group_progress(group_id)
            
            # Mark group as completed
            with self.lock:
                if group_id in self.batch_groups:
                    batch_group = self.batch_groups[group_id]
                    if batch_group.failed_batches > 0:
                        batch_group.status = "completed_with_errors"
                    else:
                        batch_group.status = "completed"
            
            self._save_persistent_data()
            logging.info(f"Batch group {group_id} processing completed")
            
        except Exception as e:
            logging.error(f"Error monitoring batch group {group_id}: {e}")
            with self.lock:
                if group_id in self.batch_groups:
                    self.batch_groups[group_id].status = "error"
    
    
    def _update_group_progress(self, group_id: str):
        """Update batch group progress counters."""
        with self.lock:
            if group_id not in self.batch_groups:
                return
            
            batch_group = self.batch_groups[group_id]
            
            # Count batch statuses
            completed = 0
            failed = 0
            in_progress = 0
            
            for batch in batch_group.batches:
                batch_id = batch['batch_id']
                if batch_id in self.batch_results:
                    status = self.batch_results[batch_id].status
                    if status == BatchStatus.COMPLETED:
                        completed += 1
                    elif status == BatchStatus.FAILED:
                        failed += 1
                    elif status == BatchStatus.IN_PROGRESS:
                        in_progress += 1
            
            batch_group.completed_batches = completed
            batch_group.failed_batches = failed
            batch_group.in_progress_batches = in_progress
    
    
    def get_batch_group_status(self, group_id: str) -> Optional[Dict[str, Any]]:
        """Get current status of a batch group."""
        if group_id not in self.batch_groups:
            return None
        
        with self.lock:
            batch_group = self.batch_groups[group_id]
            self._update_group_progress(group_id)
            
            # Get detailed batch status
            batch_statuses = []
            for batch in batch_group.batches:
                batch_id = batch['batch_id']
                if batch_id in self.batch_results:
                    result = self.batch_results[batch_id]
                    batch_statuses.append({
                        'batch_id': batch_id,
                        'status': result.status.value,
                        'keywords_processed': result.keywords_processed,
                        'timing_ms': result.timing_ms,
                        'error': result.error
                    })
                else:
                    batch_statuses.append({
                        'batch_id': batch_id,
                        'status': 'pending',
                        'keywords_processed': 0,
                        'timing_ms': None,
                        'error': None
                    })
            
            return {
                'group_id': group_id,
                'status': batch_group.status,
                'total_batches': batch_group.total_batches,
                'total_keywords': batch_group.total_keywords,
                'completed_batches': batch_group.completed_batches,
                'failed_batches': batch_group.failed_batches,
                'in_progress_batches': batch_group.in_progress_batches,
                'created_at': batch_group.created_at,
                'batches': batch_statuses
            }
    
    
    def get_batch_group_results(self, group_id: str) -> Optional[List[Dict[str, Any]]]:
        """Get results for all completed batches in a group."""
        if group_id not in self.batch_groups:
            return None
        
        batch_group = self.batch_groups[group_id]
        results = []
        
        with self.lock:
            for batch in batch_group.batches:
                batch_id = batch['batch_id']
                if batch_id in self.batch_results:
                    result = self.batch_results[batch_id]
                    if result.status == BatchStatus.COMPLETED and result.result_data:
                        results.append(result.result_data)
        
        return results
    
    
    def _save_batch_result(self, batch_result: BatchResult):
        """Save individual batch result to file."""
        result_file = os.path.join(self.results_dir, f"{batch_result.batch_id}.json")
        with open(result_file, 'w') as f:
            json.dump(asdict(batch_result), f, indent=2, default=str)
    
    
    def _save_persistent_data(self):
        """Save batch groups and results to persistent storage."""
        state_file = os.path.join(self.results_dir, "batch_state.json")
        
        # Convert to serializable format
        state_data = {
            'batch_groups': {},
            'batch_results': {}
        }
        
        for group_id, group in self.batch_groups.items():
            state_data['batch_groups'][group_id] = asdict(group)
        
        for batch_id, result in self.batch_results.items():
            result_dict = asdict(result)
            result_dict['status'] = result.status.value  # Convert enum to string
            state_data['batch_results'][batch_id] = result_dict
        
        with open(state_file, 'w') as f:
            json.dump(state_data, f, indent=2, default=str)
    
    
    def _load_persistent_data(self):
        """Load batch groups and results from persistent storage."""
        state_file = os.path.join(self.results_dir, "batch_state.json")
        
        if not os.path.exists(state_file):
            return
        
        try:
            with open(state_file, 'r') as f:
                state_data = json.load(f)
            
            # Load batch groups
            for group_id, group_data in state_data.get('batch_groups', {}).items():
                batch_group = BatchGroup(**group_data)
                self.batch_groups[group_id] = batch_group
            
            # Load batch results
            for batch_id, result_data in state_data.get('batch_results', {}).items():
                result_data['status'] = BatchStatus(result_data['status'])  # Convert string to enum
                batch_result = BatchResult(**result_data)
                self.batch_results[batch_id] = batch_result
            
            logging.info(f"Loaded {len(self.batch_groups)} batch groups from persistent storage")
            
        except Exception as e:
            logging.error(f"Error loading persistent data: {e}")


# Global batch service instance
_batch_service = None


def get_batch_service() -> BatchService:
    """Get the global batch service instance."""
    global _batch_service
    if _batch_service is None:
        _batch_service = BatchService()
    return _batch_service