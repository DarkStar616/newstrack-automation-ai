#!/usr/bin/env python3
"""
Newstrack Batch Runner

Processes large keyword datasets in batches with idempotency, retry logic,
and comprehensive audit logging.

Usage:
    python run.py --input data/keywords.csv --batch-size 300 --dry-run
    python run.py --input data/keywords.csv --depth fast
    python run.py --estimate --input data/keywords.csv
"""

import os
import sys
import csv
import json
import yaml
import time
import argparse
import logging
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))


class BatchRunner:
    """Main batch runner for processing keyword datasets."""
    
    def __init__(self, config_file: str = "config.yml"):
        self.config = self.load_config(config_file)
        self.setup_logging()
        self.session = requests.Session()
        self.session.timeout = self.config.get('timeout_seconds', 300)
        
    def load_config(self, config_file: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                return yaml.safe_load(f)
        else:
            # Default configuration
            return {
                'batch_size': 300,
                'max_retries': 3,
                'api_base_url': 'http://localhost:3000/api',
                'timeout_seconds': 300,
                'default_sector': 'general',
                'default_date': datetime.now().strftime('%Y-%m'),
                'search_mode': 'off',
                'log_level': 'INFO'
            }
    
    def setup_logging(self):
        """Setup logging configuration."""
        log_level = getattr(logging, self.config.get('log_level', 'INFO').upper())
        log_file = self.config.get('log_file', 'batch_runner.log')
        
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def load_keywords_from_csv(self, file_path: str) -> List[Dict[str, str]]:
        """
        Load keywords from CSV file.
        
        Expected CSV format:
        sector,company,keywords,date
        insurance,Santam,"keyword1,keyword2,keyword3",2025-08
        """
        keywords_data = []
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Input file not found: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Parse keywords (comma-separated or newline-separated)
                keywords_str = row.get('keywords', '')
                if ',' in keywords_str:
                    keywords = [kw.strip() for kw in keywords_str.split(',') if kw.strip()]
                else:
                    keywords = [kw.strip() for kw in keywords_str.split('\n') if kw.strip()]
                
                keywords_data.append({
                    'sector': row.get('sector', self.config['default_sector']),
                    'company': row.get('company', ''),
                    'keywords': keywords,
                    'date': row.get('date', self.config['default_date'])
                })
        
        self.logger.info(f"Loaded {len(keywords_data)} keyword sets from {file_path}")
        return keywords_data
    
    def split_into_batches(self, keywords: List[str], batch_size: int) -> List[List[str]]:
        """Split keywords into batches."""
        batches = []
        for i in range(0, len(keywords), batch_size):
            batch = keywords[i:i + batch_size]
            batches.append(batch)
        return batches
    
    def estimate_processing_cost(self, keywords_data: List[Dict[str, str]]) -> Dict[str, Any]:
        """Estimate processing costs and time."""
        total_keywords = sum(len(data['keywords']) for data in keywords_data)
        batch_size = self.config['batch_size']
        total_batches = sum(
            len(self.split_into_batches(data['keywords'], batch_size)) 
            for data in keywords_data
        )
        
        # Rough estimates
        avg_tokens_per_keyword = 10
        total_input_tokens = total_keywords * avg_tokens_per_keyword * 3  # 3 steps
        total_output_tokens = total_keywords * 15  # Expansion factor
        
        # Cost estimates (based on gpt-4.1-mini pricing)
        input_cost_per_1m = 0.40  # USD
        output_cost_per_1m = 1.60  # USD
        
        estimated_cost = (
            (total_input_tokens / 1_000_000) * input_cost_per_1m +
            (total_output_tokens / 1_000_000) * output_cost_per_1m
        )
        
        # Time estimates
        avg_time_per_batch = 30  # seconds
        estimated_time_minutes = (total_batches * avg_time_per_batch) / 60
        
        return {
            'total_keywords': total_keywords,
            'total_batches': total_batches,
            'estimated_tokens': {
                'input': total_input_tokens,
                'output': total_output_tokens,
                'total': total_input_tokens + total_output_tokens
            },
            'estimated_cost_usd': round(estimated_cost, 2),
            'estimated_time_minutes': round(estimated_time_minutes, 1),
            'batch_size': batch_size
        }
    
    def process_batch_via_api(self, 
                            keywords: List[str], 
                            sector: str, 
                            company: str, 
                            date: str,
                            idempotency_key: str) -> Dict[str, Any]:
        """Process a batch via the API."""
        url = f"{self.config['api_base_url']}/process-all"
        
        payload = {
            'sector': sector,
            'company': company,
            'keywords': '\n'.join(keywords),
            'date': date
        }
        
        headers = {
            'Content-Type': 'application/json',
            'X-Idempotency-Key': idempotency_key
        }
        
        try:
            response = self.session.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"API request failed: {e}")
            raise
    
    def run_batch_processing(self, 
                           input_file: str,
                           batch_size: Optional[int] = None,
                           depth: str = 'off',
                           dry_run: bool = False,
                           idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Run the main batch processing workflow.
        
        Args:
            input_file: Path to input CSV file
            batch_size: Override default batch size
            depth: Search depth (off, fast, deep)
            dry_run: If True, validate input and show plan without processing
            idempotency_key: Custom idempotency key for re-runs
            
        Returns:
            Dictionary with processing results and statistics
        """
        start_time = time.time()
        
        # Load input data
        keywords_data = self.load_keywords_from_csv(input_file)
        
        # Use provided batch size or default
        effective_batch_size = batch_size or self.config['batch_size']
        
        # Generate idempotency key if not provided
        if not idempotency_key:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            idempotency_key = f"batch_{timestamp}"
        
        # Calculate processing plan
        total_keywords = sum(len(data['keywords']) for data in keywords_data)
        all_batches = []
        
        for i, data in enumerate(keywords_data):
            batches = self.split_into_batches(data['keywords'], effective_batch_size)
            for j, batch in enumerate(batches):
                all_batches.append({
                    'dataset_index': i,
                    'batch_index': j,
                    'sector': data['sector'],
                    'company': data['company'],
                    'date': data['date'],
                    'keywords': batch,
                    'idempotency_key': f"{idempotency_key}_{i}_{j}"
                })
        
        self.logger.info(f"Processing plan: {len(all_batches)} batches, {total_keywords} total keywords")
        
        if dry_run:
            estimate = self.estimate_processing_cost(keywords_data)
            return {
                'dry_run': True,
                'plan': {
                    'total_datasets': len(keywords_data),
                    'total_batches': len(all_batches),
                    'total_keywords': total_keywords,
                    'batch_size': effective_batch_size,
                    'idempotency_key': idempotency_key
                },
                'estimate': estimate
            }
        
        # Process batches
        results = {
            'success': True,
            'processed_batches': 0,
            'failed_batches': 0,
            'total_keywords_processed': 0,
            'batch_results': [],
            'errors': [],
            'timing': {
                'start_time': start_time,
                'end_time': None,
                'duration_seconds': None
            }
        }
        
        for batch_info in all_batches:
            try:
                self.logger.info(f"Processing batch {batch_info['batch_index']} of dataset {batch_info['dataset_index']}")
                
                batch_result = self.process_batch_via_api(
                    keywords=batch_info['keywords'],
                    sector=batch_info['sector'],
                    company=batch_info['company'],
                    date=batch_info['date'],
                    idempotency_key=batch_info['idempotency_key']
                )
                
                results['processed_batches'] += 1
                results['total_keywords_processed'] += len(batch_info['keywords'])
                results['batch_results'].append({
                    'batch_info': batch_info,
                    'result': batch_result,
                    'success': True
                })
                
                self.logger.info(f"Batch completed successfully: {len(batch_info['keywords'])} keywords processed")
                
            except Exception as e:
                error_msg = f"Batch failed: {str(e)}"
                self.logger.error(error_msg)
                
                results['failed_batches'] += 1
                results['errors'].append({
                    'batch_info': batch_info,
                    'error': error_msg
                })
                results['batch_results'].append({
                    'batch_info': batch_info,
                    'result': None,
                    'success': False,
                    'error': error_msg
                })
                
                # Continue processing other batches
                continue
        
        # Finalize results
        end_time = time.time()
        results['timing']['end_time'] = end_time
        results['timing']['duration_seconds'] = end_time - start_time
        
        if results['failed_batches'] > 0:
            results['success'] = False
        
        self.logger.info(f"Batch processing completed: {results['processed_batches']} successful, {results['failed_batches']} failed")
        
        return results


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description='Newstrack Batch Runner')
    
    parser.add_argument('--input', type=str, default='data/keywords.csv',
                       help='Input CSV file path')
    parser.add_argument('--batch-size', type=int,
                       help='Override default batch size')
    parser.add_argument('--depth', choices=['off', 'fast', 'deep'], default='off',
                       help='Search depth mode')
    parser.add_argument('--dry-run', action='store_true',
                       help='Validate input and show plan without processing')
    parser.add_argument('--estimate', action='store_true',
                       help='Show cost and time estimates')
    parser.add_argument('--idempotency-key', type=str,
                       help='Custom idempotency key for re-runs')
    parser.add_argument('--config', type=str, default='config.yml',
                       help='Configuration file path')
    
    args = parser.parse_args()
    
    try:
        runner = BatchRunner(config_file=args.config)
        
        if args.estimate:
            # Show estimates only
            keywords_data = runner.load_keywords_from_csv(args.input)
            estimate = runner.estimate_processing_cost(keywords_data)
            
            print("\n=== PROCESSING ESTIMATE ===")
            print(f"Total keywords: {estimate['total_keywords']:,}")
            print(f"Total batches: {estimate['total_batches']:,}")
            print(f"Batch size: {estimate['batch_size']}")
            print(f"Estimated tokens: {estimate['estimated_tokens']['total']:,}")
            print(f"Estimated cost: ${estimate['estimated_cost_usd']}")
            print(f"Estimated time: {estimate['estimated_time_minutes']} minutes")
            return
        
        # Run processing
        results = runner.run_batch_processing(
            input_file=args.input,
            batch_size=args.batch_size,
            depth=args.depth,
            dry_run=args.dry_run,
            idempotency_key=args.idempotency_key
        )
        
        if args.dry_run:
            print("\n=== DRY RUN RESULTS ===")
            print(json.dumps(results, indent=2))
        else:
            print("\n=== PROCESSING RESULTS ===")
            print(f"Success: {results['success']}")
            print(f"Processed batches: {results['processed_batches']}")
            print(f"Failed batches: {results['failed_batches']}")
            print(f"Total keywords processed: {results['total_keywords_processed']}")
            print(f"Duration: {results['timing']['duration_seconds']:.1f} seconds")
            
            if results['errors']:
                print(f"\nErrors: {len(results['errors'])}")
                for error in results['errors'][:5]:  # Show first 5 errors
                    print(f"  - {error['error']}")
    
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

