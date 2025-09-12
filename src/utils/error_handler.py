"""
Standardized error handling for the Newstrack automation system.
"""
import traceback
from typing import Dict, Any, Optional
from flask import current_app, jsonify
from werkzeug.exceptions import HTTPException


class NewstrackError(Exception):
    """Base exception for Newstrack automation errors."""
    
    def __init__(self, message: str, error_code: str = None, details: Dict[str, Any] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or 'NEWSTRACK_ERROR'
        self.details = details or {}


class ValidationError(NewstrackError):
    """Raised when input validation fails."""
    
    def __init__(self, message: str, field: str = None, details: Dict[str, Any] = None):
        super().__init__(message, 'VALIDATION_ERROR', details)
        self.field = field


class ProcessingError(NewstrackError):
    """Raised when keyword processing fails."""
    
    def __init__(self, message: str, step: str = None, details: Dict[str, Any] = None):
        super().__init__(message, 'PROCESSING_ERROR', details)
        self.step = step


class GuardrailsError(NewstrackError):
    """Raised when guardrails checks fail."""
    
    def __init__(self, message: str, guardrail_type: str = None, details: Dict[str, Any] = None):
        super().__init__(message, 'GUARDRAILS_ERROR', details)
        self.guardrail_type = guardrail_type


class LLMError(NewstrackError):
    """Raised when LLM API calls fail."""
    
    def __init__(self, message: str, provider: str = None, model: str = None, details: Dict[str, Any] = None):
        super().__init__(message, 'LLM_ERROR', details)
        self.provider = provider
        self.model = model


class AuditError(NewstrackError):
    """Raised when audit logging fails."""
    
    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(message, 'AUDIT_ERROR', details)


def create_error_response(status_code: int, 
                         message: str, 
                         error_code: str = None,
                         details: Dict[str, Any] = None,
                         request_id: str = None) -> tuple:
    """
    Create a standardized error response.
    
    Args:
        status_code: HTTP status code
        message: Error message
        error_code: Internal error code
        details: Additional error details
        request_id: Request ID for tracking
        
    Returns:
        Tuple of (response, status_code)
    """
    error_response = {
        'error': message,
        'error_code': error_code or 'UNKNOWN_ERROR',
        'status_code': status_code,
        'timestamp': current_app.config.get('REQUEST_TIMESTAMP'),
        'request_id': request_id or current_app.config.get('REQUEST_ID')
    }
    
    if details:
        error_response['details'] = details
    
    # Log the error
    current_app.logger.error(f"Error {status_code}: {message}", extra={
        'error_code': error_code,
        'details': details,
        'request_id': request_id
    })
    
    return jsonify(error_response), status_code


def handle_newstrack_error(error: NewstrackError, request_id: str = None) -> tuple:
    """Handle NewstrackError exceptions."""
    status_code = 400
    
    if isinstance(error, ValidationError):
        status_code = 400
    elif isinstance(error, ProcessingError):
        status_code = 422
    elif isinstance(error, GuardrailsError):
        status_code = 422
    elif isinstance(error, LLMError):
        status_code = 502
    elif isinstance(error, AuditError):
        status_code = 500
    
    return create_error_response(
        status_code=status_code,
        message=error.message,
        error_code=error.error_code,
        details=error.details,
        request_id=request_id
    )


def handle_http_exception(error: HTTPException, request_id: str = None) -> tuple:
    """Handle HTTP exceptions."""
    return create_error_response(
        status_code=error.code,
        message=error.description,
        error_code='HTTP_ERROR',
        request_id=request_id
    )


def handle_generic_exception(error: Exception, request_id: str = None) -> tuple:
    """Handle generic exceptions."""
    # Log the full traceback for debugging
    current_app.logger.error(f"Unhandled exception: {str(error)}", extra={
        'traceback': traceback.format_exc(),
        'request_id': request_id
    })
    
    # Don't expose internal error details in production
    if current_app.config.get('DEBUG', False):
        details = {
            'exception_type': type(error).__name__,
            'traceback': traceback.format_exc()
        }
    else:
        details = None
    
    return create_error_response(
        status_code=500,
        message='An internal server error occurred',
        error_code='INTERNAL_ERROR',
        details=details,
        request_id=request_id
    )


def register_error_handlers(app):
    """Register error handlers with the Flask app."""
    
    @app.errorhandler(NewstrackError)
    def handle_newstrack_error_handler(error):
        request_id = getattr(app, 'current_request_id', None)
        return handle_newstrack_error(error, request_id)
    
    @app.errorhandler(HTTPException)
    def handle_http_exception_handler(error):
        request_id = getattr(app, 'current_request_id', None)
        return handle_http_exception(error, request_id)
    
    @app.errorhandler(Exception)
    def handle_generic_exception_handler(error):
        request_id = getattr(app, 'current_request_id', None)
        return handle_generic_exception(error, request_id)


def validate_request_data(data: Dict[str, Any], required_fields: list, optional_fields: list = None) -> None:
    """
    Validate request data against required and optional fields.
    
    Args:
        data: Request data to validate
        required_fields: List of required field names
        optional_fields: List of optional field names
        
    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(data, dict):
        raise ValidationError("Request data must be a JSON object")
    
    # Check required fields
    missing_fields = []
    for field in required_fields:
        if field not in data or data[field] is None or data[field] == '':
            missing_fields.append(field)
    
    if missing_fields:
        raise ValidationError(
            f"Missing required fields: {', '.join(missing_fields)}",
            details={'missing_fields': missing_fields}
        )
    
    # Check for unexpected fields
    allowed_fields = set(required_fields)
    if optional_fields:
        allowed_fields.update(optional_fields)
    
    unexpected_fields = set(data.keys()) - allowed_fields
    if unexpected_fields:
        raise ValidationError(
            f"Unexpected fields: {', '.join(unexpected_fields)}",
            details={'unexpected_fields': list(unexpected_fields)}
        )


def validate_keywords(keywords: str) -> list:
    """
    Validate and parse keywords string.
    
    Args:
        keywords: Keywords string (newline or comma separated)
        
    Returns:
        List of cleaned keywords
        
    Raises:
        ValidationError: If keywords are invalid
    """
    if not keywords or not keywords.strip():
        raise ValidationError("Keywords cannot be empty")
    
    # Split by newlines first, then by commas
    keyword_list = []
    for line in keywords.strip().split('\n'):
        line = line.strip()
        if line:
            if ',' in line:
                # Split by comma and clean each keyword
                for keyword in line.split(','):
                    keyword = keyword.strip()
                    if keyword:
                        keyword_list.append(keyword)
            else:
                keyword_list.append(line)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_keywords = []
    for keyword in keyword_list:
        if keyword.lower() not in seen:
            seen.add(keyword.lower())
            unique_keywords.append(keyword)
    
    if not unique_keywords:
        raise ValidationError("No valid keywords found")
    
    if len(unique_keywords) > 1000:
        raise ValidationError(
            f"Too many keywords ({len(unique_keywords)}). Maximum allowed is 1000.",
            details={'keyword_count': len(unique_keywords)}
        )
    
    return unique_keywords


def validate_sector(sector: str) -> str:
    """
    Validate sector field.
    
    Args:
        sector: Sector string
        
    Returns:
        Cleaned sector string
        
    Raises:
        ValidationError: If sector is invalid
    """
    if not sector or not sector.strip():
        raise ValidationError("Sector cannot be empty")
    
    sector = sector.strip()
    
    if len(sector) > 100:
        raise ValidationError(
            f"Sector name too long ({len(sector)} characters). Maximum allowed is 100.",
            details={'sector_length': len(sector)}
        )
    
    return sector


def validate_company(company: str) -> Optional[str]:
    """
    Validate company field.
    
    Args:
        company: Company string (optional)
        
    Returns:
        Cleaned company string or None
        
    Raises:
        ValidationError: If company is invalid
    """
    if not company:
        return None
    
    company = company.strip()
    if not company:
        return None
    
    if len(company) > 100:
        raise ValidationError(
            f"Company name too long ({len(company)} characters). Maximum allowed is 100.",
            details={'company_length': len(company)}
        )
    
    return company


def validate_date(date: str) -> str:
    """
    Validate date field.
    
    Args:
        date: Date string
        
    Returns:
        Cleaned date string
        
    Raises:
        ValidationError: If date is invalid
    """
    if not date or not date.strip():
        raise ValidationError("Date cannot be empty")
    
    date = date.strip()
    
    if len(date) > 50:
        raise ValidationError(
            f"Date string too long ({len(date)} characters). Maximum allowed is 50.",
            details={'date_length': len(date)}
        )
    
    return date

