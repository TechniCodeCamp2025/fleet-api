"""
CSV utilities for FastAPI endpoints.
Helper functions for parsing and validating CSV files.
"""
import csv
import io
from typing import List, Dict, Any, Tuple, Optional, Callable
from datetime import datetime


def parse_csv_to_dict(content: bytes, encoding: str = 'utf-8') -> List[Dict[str, str]]:
    """
    Parse CSV bytes content to list of dictionaries.
    
    Args:
        content: Raw bytes from uploaded file
        encoding: Text encoding (default: utf-8)
    
    Returns:
        List of row dictionaries
    """
    text = content.decode(encoding)
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def validate_csv_columns(
    rows: List[Dict[str, str]], 
    required_columns: List[str],
    file_name: str = "CSV"
) -> Tuple[bool, Optional[str]]:
    """
    Validate that CSV has required columns.
    
    Args:
        rows: Parsed CSV rows
        required_columns: List of required column names
        file_name: Name for error messages
    
    Returns:
        (is_valid, error_message)
    """
    if not rows:
        return False, f"{file_name}: File is empty"
    
    headers = set(rows[0].keys())
    missing = set(required_columns) - headers
    
    if missing:
        return False, f"{file_name}: Missing required columns: {', '.join(missing)}"
    
    return True, None


def validate_row_types(
    row: Dict[str, str],
    type_spec: Dict[str, type],
    row_num: int = 0,
    file_name: str = "CSV"
) -> Tuple[bool, Optional[str]]:
    """
    Validate data types in a CSV row.
    
    Args:
        row: CSV row as dictionary
        type_spec: Dictionary mapping column names to expected types
        row_num: Row number for error messages
        file_name: File name for error messages
    
    Returns:
        (is_valid, error_message)
    """
    for col_name, expected_type in type_spec.items():
        value = row.get(col_name, '').strip()
        
        # Skip empty values and special markers
        if not value or value.upper() == 'N/A':
            continue
        
        try:
            if expected_type == int:
                int(value)
            elif expected_type == float:
                float(value)
            elif expected_type == datetime:
                # Try to parse datetime
                datetime.fromisoformat(value.replace(' ', 'T'))
            # str type always passes
        except (ValueError, TypeError) as e:
            return False, f"{file_name} row {row_num}: Column '{col_name}' has invalid {expected_type.__name__} value: '{value}'"
    
    return True, None


def csv_to_preview_string(
    rows: List[Dict[str, str]],
    max_rows: int = 10,
    max_col_width: int = 20
) -> str:
    """
    Format CSV rows as a pretty preview string.
    
    Args:
        rows: CSV rows
        max_rows: Maximum rows to include
        max_col_width: Maximum width for each column
    
    Returns:
        Formatted string preview
    """
    if not rows:
        return "(empty)"
    
    headers = list(rows[0].keys())
    preview_rows = rows[:max_rows]
    
    # Build preview
    lines = []
    lines.append(" | ".join(h[:max_col_width] for h in headers))
    lines.append("-" * (len(lines[0]) + 10))
    
    for row in preview_rows:
        values = [str(row.get(h, ''))[:max_col_width] for h in headers]
        lines.append(" | ".join(values))
    
    return "\n".join(lines)


def count_csv_rows(content: bytes, encoding: str = 'utf-8') -> int:
    """
    Count total rows in CSV (excluding header).
    
    Args:
        content: Raw bytes from CSV file
        encoding: Text encoding
    
    Returns:
        Number of data rows
    """
    text = content.decode(encoding)
    reader = csv.DictReader(io.StringIO(text))
    return sum(1 for _ in reader)


def safe_csv_value(value: str, target_type: type, default: Any = None) -> Any:
    """
    Safely convert CSV string value to target type.
    
    Args:
        value: String value from CSV
        target_type: Type to convert to (int, float, str, datetime)
        default: Default value if conversion fails
    
    Returns:
        Converted value or default
    """
    value = value.strip()
    
    if not value or value.upper() == 'N/A':
        return default
    
    try:
        if target_type == int:
            return int(value)
        elif target_type == float:
            return float(value)
        elif target_type == datetime:
            return datetime.fromisoformat(value.replace(' ', 'T'))
        else:
            return str(value)
    except (ValueError, TypeError):
        return default


def extract_csv_column(rows: List[Dict[str, str]], column_name: str) -> List[Any]:
    """
    Extract a single column from CSV rows.
    
    Args:
        rows: CSV rows
        column_name: Name of column to extract
    
    Returns:
        List of values from that column
    """
    return [row.get(column_name) for row in rows]


def filter_csv_rows(
    rows: List[Dict[str, str]],
    filter_func: Callable[[Dict[str, str]], bool]
) -> List[Dict[str, str]]:
    """
    Filter CSV rows using a custom function.
    
    Args:
        rows: CSV rows
        filter_func: Function that takes a row dict and returns bool
    
    Returns:
        Filtered list of rows
    """
    return [row for row in rows if filter_func(row)]
