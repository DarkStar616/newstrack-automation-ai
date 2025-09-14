"""
CSV ingestion utility with encoding detection, header parsing, and auto-batching.
Supports UTF-8, Windows-1252, and various CSV formats with robust validation.
"""
import os
import io
import csv
import chardet
import uuid
import logging
from typing import List, Dict, Optional, Any, Union, Tuple
from datetime import datetime


def load_keywords_from_csv(csv_file: Union[str, io.StringIO, io.BytesIO]) -> List[Dict[str, Optional[str]]]:
    """
    Load keywords from CSV file with automatic encoding detection.
    
    Args:
        csv_file: Path to CSV file or StringIO/BytesIO object from upload
        
    Returns:
        List of dictionaries with keys:
        - keyword: The keyword string (required)
        - category: Optional category (company/industry/regulatory)  
        - source_location: Optional source location rule
        
    Expected CSV columns:
    - Keyword (required)
    - Category (optional: company/industry/regulatory)
    - Source location (optional: blank | "South Africa" | "!South Africa")
    """
    if isinstance(csv_file, str):
        # File path
        if not os.path.exists(csv_file):
            raise FileNotFoundError(f"CSV file not found: {csv_file}")
        return _load_from_file_path(csv_file)
    else:
        # BytesIO or StringIO from upload
        return _load_from_stream(csv_file)


def _load_from_file_path(file_path: str) -> List[Dict[str, Optional[str]]]:
    """Load CSV from file path with encoding detection."""
    # Detect encoding
    with open(file_path, 'rb') as f:
        raw_data = f.read()
        encoding_result = chardet.detect(raw_data)
        encoding = encoding_result.get('encoding', 'utf-8')
        
    # Handle BOM for UTF-8
    if encoding.lower().startswith('utf-8'):
        encoding = 'utf-8-sig'
    
    try:
        with open(file_path, 'r', encoding=encoding, newline='') as f:
            return _parse_csv_content(f)
    except UnicodeDecodeError:
        # Fallback to common encodings
        for fallback_encoding in ['utf-8', 'windows-1252', 'latin-1', 'ascii']:
            try:
                with open(file_path, 'r', encoding=fallback_encoding, newline='') as f:
                    logging.warning(f"Using fallback encoding: {fallback_encoding}")
                    return _parse_csv_content(f)
            except UnicodeDecodeError:
                continue
        raise ValueError(f"Unable to decode CSV file with any supported encoding")


def _load_from_stream(csv_stream: Union[io.StringIO, io.BytesIO]) -> List[Dict[str, Optional[str]]]:
    """Load CSV from StringIO or BytesIO stream."""
    csv_stream.seek(0)  # Reset to beginning
    
    if isinstance(csv_stream, io.BytesIO):
        # Detect encoding for BytesIO
        raw_data = csv_stream.read()
        csv_stream.seek(0)
        
        encoding_result = chardet.detect(raw_data)
        encoding = encoding_result.get('encoding', 'utf-8')
        
        # Handle BOM
        if encoding.lower().startswith('utf-8'):
            encoding = 'utf-8-sig'
        
        try:
            text_content = raw_data.decode(encoding)
            text_stream = io.StringIO(text_content)
            return _parse_csv_content(text_stream)
        except UnicodeDecodeError:
            # Try fallback encodings
            for fallback_encoding in ['utf-8', 'windows-1252', 'latin-1']:
                try:
                    text_content = raw_data.decode(fallback_encoding)
                    text_stream = io.StringIO(text_content)
                    logging.warning(f"Using fallback encoding: {fallback_encoding}")
                    return _parse_csv_content(text_stream)
                except UnicodeDecodeError:
                    continue
            raise ValueError("Unable to decode CSV content with any supported encoding")
    else:
        # StringIO - already decoded
        return _parse_csv_content(csv_stream)


def _parse_csv_content(csv_file) -> List[Dict[str, Optional[str]]]:
    """Parse CSV content with auto-detection of delimiter and format."""
    # Read first few lines to detect format
    first_lines = []
    csv_file.seek(0)
    for i, line in enumerate(csv_file):
        first_lines.append(line)
        if i >= 5:  # Read first 6 lines for detection
            break
    
    csv_file.seek(0)
    
    # Detect delimiter
    sample_content = ''.join(first_lines)
    sniffer = csv.Sniffer()
    
    try:
        dialect = sniffer.sniff(sample_content, delimiters=',;\t|')
    except csv.Error:
        # Default to comma if detection fails
        dialect = csv.excel
        dialect.delimiter = ','
    
    # Parse CSV with detected/default dialect
    reader = csv.DictReader(csv_file, dialect=dialect)
    
    # Handle headerless CSV
    if not _has_header(first_lines, dialect.delimiter):
        csv_file.seek(0)
        reader = csv.reader(csv_file, dialect=dialect)
        rows = list(reader)
        
        if not rows:
            return []
        
        # Create headers for headerless CSV
        headers = ['Keyword', 'Category', 'Source location'][:len(rows[0])]
        data = []
        
        for row in rows:
            row_dict = {}
            for i, value in enumerate(row):
                if i < len(headers):
                    row_dict[headers[i]] = value.strip() if value else None
            data.append(row_dict)
        
        return _process_raw_data(data)
    else:
        # Has header - use DictReader
        data = []
        for row in reader:
            # Clean up the row data
            clean_row = {}
            for key, value in row.items():
                clean_key = key.strip() if key else 'Unknown'
                clean_value = value.strip() if value else None
                clean_row[clean_key] = clean_value
            data.append(clean_row)
        
        return _process_raw_data(data)


def _has_header(first_lines: List[str], delimiter: str) -> bool:
    """Detect if CSV has a header row."""
    if not first_lines:
        return False
    
    first_row = first_lines[0].strip().split(delimiter)
    
    # Look for common header patterns
    header_keywords = ['keyword', 'category', 'source', 'location', 'type', 'term']
    
    for cell in first_row:
        cell_lower = cell.lower().strip()
        if any(keyword in cell_lower for keyword in header_keywords):
            return True
    
    # If we have multiple lines, check if first row looks different from second
    if len(first_lines) > 1:
        second_row = first_lines[1].strip().split(delimiter)
        
        # Basic heuristic: if first row has non-numeric data and second row has different patterns
        first_numeric = sum(1 for cell in first_row if cell.strip().replace('.', '').isdigit())
        second_numeric = sum(1 for cell in second_row if cell.strip().replace('.', '').isdigit())
        
        if first_numeric == 0 and second_numeric > 0:
            return True
    
    return False


def _process_raw_data(data: List[Dict[str, Any]]) -> List[Dict[str, Optional[str]]]:
    """Process raw CSV data into normalized keyword format."""
    results = []
    
    if not data:
        return results
    
    # Normalize column names (case-insensitive matching)
    sample_row = data[0]
    columns = {col.lower().strip(): col for col in sample_row.keys() if col}
    
    keyword_col = _find_column(columns, ['keyword', 'keywords', 'term', 'terms'])
    category_col = _find_column(columns, ['category', 'type', 'classification'])
    source_location_col = _find_column(columns, ['source location', 'source_location', 'region', 'location'])
    
    if not keyword_col:
        # Try first column as keyword if no header match
        first_col = list(sample_row.keys())[0] if sample_row.keys() else None
        if first_col:
            keyword_col = first_col
        else:
            raise ValueError("No keyword column found. Expected 'Keyword' column or first column with keyword data.")
    
    for row in data:
        keyword = str(row.get(keyword_col, '')).strip() if row.get(keyword_col) else None
        
        if not keyword or keyword.lower() in ['nan', 'none', '', 'null']:
            continue
            
        category = None
        if category_col and row.get(category_col):
            category_value = row.get(category_col)
            if category_value is not None:
                category = str(category_value).strip()
                if category.lower() in ['nan', 'none', '', 'null']:
                    category = None
        
        source_location = None  
        if source_location_col and row.get(source_location_col):
            source_location_value = row.get(source_location_col)
            if source_location_value is not None:
                source_location = str(source_location_value).strip()
                if source_location.lower() in ['nan', 'none', '', 'null']:
                    source_location = None
        
        results.append({
            'keyword': keyword,
            'category': _normalize_category(category),
            'source_location': source_location
        })
    
    # Deduplicate exact matches
    seen = set()
    deduped_results = []
    for item in results:
        key = (item['keyword'].lower(), item['category'], item['source_location'])
        if key not in seen:
            seen.add(key)
            deduped_results.append(item)
    
    return deduped_results


def _find_column(columns: Dict[str, str], candidates: List[str]) -> Optional[str]:
    """Find a column by trying multiple candidate names."""
    for candidate in candidates:
        if candidate in columns:
            return columns[candidate]
    return None


def _normalize_category(category: Optional[str]) -> Optional[str]:
    """Normalize category values to standard format."""
    if not category:
        return 'industry'  # Default category for CSV
        
    category = (category or '').lower().strip()
    
    # Map variations to standard categories
    if category in ['company', 'companies', 'corp', 'corporation']:
        return 'company'
    elif category in ['industry', 'industries', 'sector', 'business']:
        return 'industry' 
    elif category in ['regulatory', 'regulation', 'regulator', 'compliance']:
        return 'regulatory'
    else:
        return category


def extract_keywords_from_csv(csv_file: Union[str, io.StringIO, io.BytesIO]) -> Dict[str, Any]:
    """
    Extract keywords from CSV file with comprehensive processing for API routes.
    
    Args:
        csv_file: Path to CSV file or StringIO/BytesIO object from upload
        
    Returns:
        Dictionary with:
        - keywords: List of processed keyword objects
        - source_locations: Mapping of keywords to region configs
        - stats: Processing statistics
        - validation: Validation results
    """
    try:
        # Load raw data
        raw_keywords = load_keywords_from_csv(csv_file)
            
        if not raw_keywords:
            raise ValueError("No valid keywords found in CSV file")
        
        # Process keywords and build region configs
        processed_keywords = []
        source_locations = {}
        region_stats = {"global": 0, "include": 0, "exclude": 0}
        
        for i, item in enumerate(raw_keywords):
            try:
                keyword = str(item.get('keyword') or '').strip()
                category = str(item.get('category') or '').strip()
                source_location = str(item.get('source_location') or '').strip()
                
                if not keyword:
                    continue
                    
                # Parse source location according to spec
                region_config = _parse_source_location(source_location)
                
                # Build processed keyword object
                processed_keyword = {
                    'keyword': keyword,
                    'category': category or 'industry',
                    'region_mode': region_config['region_mode'],
                    'country': region_config['country']
                }
                
                processed_keywords.append(processed_keyword)
                source_locations[keyword] = region_config
                
                # Update stats
                region_stats[region_config['region_mode'].lower()] += 1
                
                # Log per specification
                logging.info(f"CSV row: {processed_keyword}")
                
            except Exception as e:
                logging.error(f"Error processing CSV row {i}: {item}, error: {str(e)}")
                raise e
        
        return {
            'keywords': processed_keywords,
            'source_locations': source_locations,
            'stats': {
                'total_keywords': len(processed_keywords),
                'region_breakdown': region_stats,
                'has_category_column': any(kw.get('category') != 'industry' for kw in processed_keywords),
                'unique_categories': list(set(kw.get('category') for kw in processed_keywords if kw.get('category')))
            },
            'validation': {
                'valid': True,
                'row_count': len(processed_keywords),
                'columns_detected': ['Keyword', 'Category', 'Source location'],
                'sample_keywords': processed_keywords[:10]
            }
        }
        
    except Exception as e:
        logging.error(f"CSV extraction failed: {str(e)}")
        return {
            'keywords': [],
            'source_locations': {},
            'stats': {'total_keywords': 0, 'region_breakdown': {}},
            'validation': {'valid': False, 'error': str(e)}
        }


def _parse_source_location(source_location: str) -> Dict[str, Optional[str]]:
    """
    Parse source location string according to specification.
    
    Rules:
    - blank / NA / null -> region_mode="GLOBAL"
    - "X" -> region_mode="INCLUDE", country="X"
    - "!X" -> region_mode="EXCLUDE", country="X"
    """
    if not source_location or (source_location and source_location.lower() in ['na', 'null', 'none', '']):
        return {'region_mode': 'GLOBAL', 'country': None}
    
    source_location = (source_location or '').strip()
    
    if source_location.startswith('!'):
        # Exclude mode: "!South Africa" -> EXCLUDE South Africa
        country = source_location[1:].strip()
        return {'region_mode': 'EXCLUDE', 'country': country if country else None}
    else:
        # Include mode: "South Africa" -> INCLUDE South Africa
        return {'region_mode': 'INCLUDE', 'country': source_location}


def create_batches(keywords: List[Dict[str, Any]], batch_size: int = 200) -> Dict[str, Any]:
    """
    Split keywords into batches of specified size for auto-batching.
    
    Args:
        keywords: List of processed keyword objects
        batch_size: Maximum keywords per batch (default 200)
        
    Returns:
        Dictionary with:
        - group_id: Unique identifier for this batch group
        - batches: List of batch objects with batch_id and keywords
        - total_batches: Total number of batches created
        - total_keywords: Total keywords across all batches
    """
    if not keywords:
        raise ValueError("No keywords provided for batching")
    
    if batch_size <= 0:
        raise ValueError("Batch size must be positive")
    
    # Generate unique group ID
    group_id = f"csv-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{str(uuid.uuid4())[:8]}"
    
    # Split into batches
    batches = []
    for i in range(0, len(keywords), batch_size):
        batch_keywords = keywords[i:i + batch_size]
        batch_id = f"{group_id}-batch-{len(batches) + 1:03d}"
        
        batches.append({
            'batch_id': batch_id,
            'keywords': batch_keywords,
            'size': len(batch_keywords),
            'status': 'pending',
            'created_at': datetime.now().isoformat(),
            'started_at': None,
            'completed_at': None,
            'timing_ms': None,
            'error': None
        })
    
    return {
        'group_id': group_id,
        'batches': batches,
        'total_batches': len(batches),
        'total_keywords': len(keywords),
        'created_at': datetime.now().isoformat(),
        'status': 'created'
    }


def analyze_csv_format(csv_file: Union[str, io.StringIO, io.BytesIO], preview_rows: int = 10) -> Dict[str, Any]:
    """
    Analyze CSV file format with detailed encoding and delimiter detection.
    
    Args:
        csv_file: Path to CSV file or stream object
        preview_rows: Number of rows to include in preview (default 10)
        
    Returns:
        Dictionary with analysis results:
        - valid: bool
        - encoding_detected: str
        - delimiter_detected: str
        - headers: list
        - preview_data: list of rows
        - total_rows: int
        - valid_keyword_count: int
        - error: str (if invalid)
    """
    try:
        # Handle different input types
        if isinstance(csv_file, str):
            with open(csv_file, 'rb') as f:
                raw_data = f.read()
        elif isinstance(csv_file, io.BytesIO):
            csv_file.seek(0)
            raw_data = csv_file.read()
        elif isinstance(csv_file, io.StringIO):
            raw_data = csv_file.getvalue().encode('utf-8')
        else:
            raise ValueError("Invalid input type for CSV file")
        
        # Detect encoding
        encoding_result = chardet.detect(raw_data)
        encoding = encoding_result['encoding'] or 'utf-8'
        
        # Handle common encoding variants
        if encoding.lower() in ['ascii', 'windows-1252']:
            encoding = 'windows-1252'
        elif 'utf-8' in encoding.lower():
            encoding = 'utf-8-sig' if raw_data.startswith(b'\xef\xbb\xbf') else 'utf-8'
        
        # Decode content
        try:
            content = raw_data.decode(encoding)
        except UnicodeDecodeError:
            # Fallback encoding chain
            for fallback in ['utf-8', 'windows-1252', 'iso-8859-1']:
                try:
                    content = raw_data.decode(fallback)
                    encoding = fallback
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise ValueError("Could not decode file with any supported encoding")
        
        # Detect delimiter by testing a sample
        sample_lines = content.split('\n')[:5]  # Use first 5 lines for detection
        sample_text = '\n'.join(sample_lines)
        
        sniffer = csv.Sniffer()
        try:
            delimiter = sniffer.sniff(sample_text, delimiters=',;\t').delimiter
        except csv.Error:
            # Fallback: count occurrences of each delimiter
            delimiter_counts = {
                ',': sum(line.count(',') for line in sample_lines),
                ';': sum(line.count(';') for line in sample_lines),
                '\t': sum(line.count('\t') for line in sample_lines)
            }
            delimiter = max(delimiter_counts, key=delimiter_counts.get)
        
        # Parse CSV content
        csv_reader = csv.reader(io.StringIO(content), delimiter=delimiter)
        rows = list(csv_reader)
        
        if not rows:
            return {
                'valid': False,
                'error': 'CSV file is empty',
                'encoding_detected': encoding,
                'delimiter_detected': delimiter
            }
        
        # Extract headers and data
        headers = rows[0] if rows else []
        data_rows = rows[1:] if len(rows) > 1 else []
        
        # Validate required columns
        header_lower = [h.lower().strip() for h in headers]
        has_keyword = any('keyword' in h for h in header_lower)
        
        if not has_keyword:
            return {
                'valid': False,
                'error': 'CSV must contain a "Keyword" column',
                'encoding_detected': encoding,
                'delimiter_detected': delimiter,
                'headers': headers
            }
        
        # Count valid keywords (non-empty keyword column)
        keyword_idx = next(i for i, h in enumerate(header_lower) if 'keyword' in h)
        valid_keywords = sum(1 for row in data_rows if len(row) > keyword_idx and row[keyword_idx].strip())
        
        # Create preview data (limit to preview_rows)
        preview_data = rows[:preview_rows + 1]  # +1 to include header
        
        return {
            'valid': True,
            'encoding_detected': encoding,
            'delimiter_detected': repr(delimiter),  # Show as string representation
            'headers': headers,
            'preview_data': preview_data,
            'total_rows': len(data_rows),
            'valid_keyword_count': valid_keywords,
            'error': None
        }
        
    except Exception as e:
        return {
            'valid': False,
            'error': str(e),
            'encoding_detected': 'unknown',
            'delimiter_detected': 'unknown',
            'headers': [],
            'preview_data': [],
            'total_rows': 0,
            'valid_keyword_count': 0
        }


def validate_csv_format(csv_file: Union[str, io.StringIO, io.BytesIO], max_rows: int = 25000) -> Dict[str, Any]:
    """
    Validate CSV file format and return info about the file.
    
    Args:
        csv_file: Path to CSV file or stream object
        max_rows: Maximum allowed rows (default 25000)
        
    Returns:
        Dictionary with validation results:
        - valid: bool
        - row_count: int
        - columns_found: list
        - has_keyword_column: bool
        - has_category_column: bool
        - has_source_location_column: bool
        - sample_rows: list (first 10 rows)
        - encoding_detected: str (for files)
        - delimiter_detected: str
    """
    try:
        keywords = load_keywords_from_csv(csv_file)
        
        if len(keywords) > max_rows:
            return {
                'valid': False,
                'error': f'File too large: {len(keywords)} rows exceeds maximum of {max_rows}. Please split the file.',
                'row_count': len(keywords),
                'columns_found': [],
                'has_keyword_column': False,
                'has_category_column': False,
                'has_source_location_column': False,
                'sample_rows': []
            }
        
        # Detect columns from sample data
        if keywords:
            sample_row = keywords[0]
            has_category = any(item.get('category') != 'industry' for item in keywords[:10])
            has_source_location = any(item.get('source_location') for item in keywords[:10])
        else:
            has_category = False
            has_source_location = False
        
        return {
            'valid': True,
            'row_count': len(keywords),
            'columns_found': ['Keyword', 'Category', 'Source location'],
            'has_keyword_column': True,  # Must be true if we loaded successfully
            'has_category_column': has_category,
            'has_source_location_column': has_source_location,
            'sample_rows': keywords[:10],
            'encoding_detected': 'auto-detected',
            'delimiter_detected': 'auto-detected'
        }
            
    except Exception as e:
        return {
            'valid': False,
            'error': str(e),
            'row_count': 0,
            'columns_found': [],
            'has_keyword_column': False,
            'has_category_column': False,
            'has_source_location_column': False,
            'sample_rows': []
        }


def create_sample_csv(file_path: str = "sample_keywords.csv"):
    """Create a sample CSV file for testing."""
    sample_data = [
        ["Keyword", "Category", "Source location"],
        ["Allianz", "company", "South Africa"],
        ["Short-term Insurance", "industry", "South Africa"],
        ["AIG", "company", ""],
        ["1st for Women", "company", "South Africa"],
        ["Prudential Authority", "regulatory", "!South Africa"],
        ["4 Sure Insurance", "company", "South Africa"],
        ["Motor vehicle insurance", "industry", ""],
        ["Santam", "company", "South Africa"],
        ["Discovery Insure", "company", "South Africa"],
        ["Hollard Insurance", "company", "!South Africa"]
    ]
    
    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(sample_data)
    
    return file_path


if __name__ == "__main__":
    # Demo usage
    sample_file = create_sample_csv()
    keywords = load_keywords_from_csv(sample_file)
    
    print(f"Loaded {len(keywords)} keywords:")
    for kw in keywords:
        print(f"  {kw['keyword']} ({kw['category']}) - {kw['source_location'] or 'Global'}")
    
    # Test auto-batching
    batches = create_batches(keywords, batch_size=3)
    print(f"\nCreated {batches['total_batches']} batches:")
    for batch in batches['batches']:
        print(f"  {batch['batch_id']}: {batch['size']} keywords")