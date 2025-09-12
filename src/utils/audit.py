"""
Audit logging utility for tracking keyword processing operations.
Writes JSONL audit logs and maintains manifest files.
"""
import os
import json
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
from flask import current_app


class AuditLogger:
    """Handles audit logging for keyword processing operations."""
    
    def __init__(self):
        self.results_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'results')
        self.ensure_results_directory()
    
    def ensure_results_directory(self):
        """Ensure results directory structure exists."""
        os.makedirs(self.results_dir, exist_ok=True)
        
        # Create current month directory
        current_month = datetime.now().strftime('%Y-%m')
        month_dir = os.path.join(self.results_dir, current_month)
        os.makedirs(month_dir, exist_ok=True)
    
    def generate_batch_id(self) -> str:
        """Generate a unique batch ID."""
        now = datetime.now()
        date_str = now.strftime('%Y-%m-%d')
        
        # Find next counter for today
        current_month = now.strftime('%Y-%m')
        month_dir = os.path.join(self.results_dir, current_month)
        
        counter = 1
        while True:
            batch_id = f"{date_str}-{counter:03d}"
            audit_file = os.path.join(month_dir, f"{batch_id}.jsonl")
            if not os.path.exists(audit_file):
                break
            counter += 1
        
        return batch_id
    
    def write_batch_audit(self, 
                         batch_id: str,
                         category: str,
                         input_keywords: List[str],
                         final_categories: Dict[str, List[str]],
                         guardrails_result: Dict[str, Any],
                         timing_ms: int,
                         step: str = 'process-all') -> str:
        """
        Write a batch audit entry to JSONL file.
        
        Returns:
            Path to the audit file
        """
        current_month = datetime.now().strftime('%Y-%m')
        month_dir = os.path.join(self.results_dir, current_month)
        audit_file = os.path.join(month_dir, f"{batch_id}.jsonl")
        
        # Calculate what was kept, added, and removed
        kept_keywords = []
        added_keywords = []
        removed_keywords = []
        
        # For now, we'll track all final keywords as "kept"
        # In a more sophisticated implementation, we'd track the diff
        for cat_keywords in final_categories.values():
            kept_keywords.extend(cat_keywords)
        
        # Extract guardrails data
        guardrails = guardrails_result.get('guardrails', {})
        leaks_blocked = guardrails.get('leaks_blocked', [])
        duplicates_dropped = guardrails.get('duplicates_dropped', [])
        counts = guardrails.get('counts', {})
        
        # Create audit entry
        audit_entry = {
            "batch_id": batch_id,
            "category": category,
            "step": step,
            "timestamp": datetime.now().isoformat(),
            "kept": kept_keywords,
            "added": added_keywords,  # TODO: Track actual additions in expansion step
            "removed": removed_keywords,  # TODO: Track actual removals in drop step
            "leaks_blocked": leaks_blocked,
            "duplicates_dropped": duplicates_dropped,
            "counts": {
                "input_total": len(input_keywords),
                "output_accounted": counts.get('output_accounted', 0),
                "added": len(added_keywords),
                "removed": len(removed_keywords),
                "duplicates_dropped": len(duplicates_dropped),
                "leaks_blocked": len(leaks_blocked)
            },
            "timing_ms": timing_ms
        }
        
        # Write to JSONL file
        try:
            with open(audit_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(audit_entry) + '\n')
            
            current_app.logger.info(f"Audit entry written to {audit_file}")
            
            # Update manifest
            self.update_manifest(batch_id, audit_entry)
            
            return audit_file
            
        except Exception as e:
            current_app.logger.error(f"Failed to write audit entry: {e}")
            raise
    
    def update_manifest(self, batch_id: str, audit_entry: Dict[str, Any]):
        """Update the monthly manifest file."""
        current_month = datetime.now().strftime('%Y-%m')
        month_dir = os.path.join(self.results_dir, current_month)
        manifest_file = os.path.join(month_dir, 'manifest.json')
        
        # Load existing manifest or create new one
        manifest = {
            "month": current_month,
            "batches": {},
            "totals": {
                "total_batches": 0,
                "total_keywords_processed": 0,
                "total_keywords_output": 0,
                "total_duplicates_dropped": 0,
                "total_leaks_blocked": 0,
                "total_timing_ms": 0
            },
            "categories": {
                "industry": {"batches": 0, "keywords": 0},
                "company": {"batches": 0, "keywords": 0},
                "regulatory": {"batches": 0, "keywords": 0}
            }
        }
        
        if os.path.exists(manifest_file):
            try:
                with open(manifest_file, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
            except Exception as e:
                current_app.logger.warning(f"Failed to load existing manifest, creating new one: {e}")
        
        # Update manifest with new batch data
        counts = audit_entry['counts']
        
        manifest['batches'][batch_id] = {
            "timestamp": audit_entry['timestamp'],
            "category": audit_entry['category'],
            "step": audit_entry['step'],
            "input_total": counts['input_total'],
            "output_accounted": counts['output_accounted'],
            "timing_ms": audit_entry['timing_ms']
        }
        
        # Update totals
        manifest['totals']['total_batches'] += 1
        manifest['totals']['total_keywords_processed'] += counts['input_total']
        manifest['totals']['total_keywords_output'] += counts['output_accounted']
        manifest['totals']['total_duplicates_dropped'] += counts['duplicates_dropped']
        manifest['totals']['total_leaks_blocked'] += counts['leaks_blocked']
        manifest['totals']['total_timing_ms'] += audit_entry['timing_ms']
        
        # Update category stats
        category = audit_entry['category']
        if category in manifest['categories']:
            manifest['categories'][category]['batches'] += 1
            manifest['categories'][category]['keywords'] += counts['output_accounted']
        
        # Write updated manifest
        try:
            with open(manifest_file, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)
            
            current_app.logger.info(f"Manifest updated: {manifest_file}")
            
        except Exception as e:
            current_app.logger.error(f"Failed to update manifest: {e}")
            raise
    
    def get_latest_manifest(self) -> Optional[Dict[str, Any]]:
        """Get the latest manifest file."""
        current_month = datetime.now().strftime('%Y-%m')
        month_dir = os.path.join(self.results_dir, current_month)
        manifest_file = os.path.join(month_dir, 'manifest.json')
        
        if os.path.exists(manifest_file):
            try:
                with open(manifest_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                current_app.logger.error(f"Failed to load manifest: {e}")
                return None
        
        return None
    
    def get_batch_audit(self, batch_id: str) -> Optional[List[Dict[str, Any]]]:
        """Get audit entries for a specific batch."""
        # Extract month from batch_id (format: YYYY-MM-DD-counter)
        try:
            date_part = batch_id.split('-')
            month = f"{date_part[0]}-{date_part[1]}"
            month_dir = os.path.join(self.results_dir, month)
            audit_file = os.path.join(month_dir, f"{batch_id}.jsonl")
            
            if os.path.exists(audit_file):
                entries = []
                with open(audit_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            entries.append(json.loads(line))
                return entries
            
        except Exception as e:
            current_app.logger.error(f"Failed to load batch audit {batch_id}: {e}")
        
        return None


def get_audit_logger() -> AuditLogger:
    """Get an audit logger instance."""
    return AuditLogger()

