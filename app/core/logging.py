"""
Structured logging infrastructure with JSON formatting and correlation IDs.
"""
import logging
import logging.config
import logging.handlers
import sys
import uuid
from contextvars import ContextVar
from typing import Any, Dict, Optional
import structlog

# Try to import json logger, fall back to basic logging if not available
try:
    from pythonjsonlogger import jsonlogger
    HAS_JSON_LOGGER = True
except ImportError:
    try:
        import json_logging
        HAS_JSON_LOGGER = True
    except ImportError:
        HAS_JSON_LOGGER = False

from app.core.config import settings

# Context variable for correlation ID
correlation_id: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)


class CorrelationIdProcessor:
    """Add correlation ID to log records."""
    
    def __call__(self, logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Add correlation ID to event dictionary."""
        corr_id = correlation_id.get()
        if corr_id:
            event_dict['correlation_id'] = corr_id
        return event_dict


class CustomJsonFormatter(logging.Formatter):
    """Custom JSON formatter with additional fields."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_record = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'name': record.name,
            'message': record.getMessage(),
        }
        
        # Add correlation ID if available
        corr_id = correlation_id.get()
        if corr_id:
            log_record['correlation_id'] = corr_id
        
        # Add service name
        log_record['service'] = 'wiki-app'
        
        # Add module and function info
        if hasattr(record, 'module'):
            log_record['module'] = record.module
        if hasattr(record, 'funcName'):
            log_record['function'] = record.funcName
        
        # Add exception info if present
        if record.exc_info:
            log_record['exception'] = self.formatException(record.exc_info)
        
        import json
        return json.dumps(log_record)


def setup_logging() -> None:
    """Configure structured logging."""
    import os
    from pathlib import Path
    
    # Ensure log directory exists
    log_dir = Path("/app/logs")
    log_dir.mkdir(exist_ok=True)
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            CorrelationIdProcessor(),
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Use production logging configuration if available
    if os.getenv("ENVIRONMENT", "development") == "production":
        try:
            from app.core.log_config import setup_production_logging
            setup_production_logging()
            return
        except ImportError:
            pass  # Fall back to basic configuration
    
    # Basic logging configuration for development
    if settings.LOG_FORMAT.lower() == 'json':
        formatter = CustomJsonFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # File handler for application logs
    file_handler = logging.handlers.RotatingFileHandler(
        '/app/logs/app.log',
        maxBytes=50 * 1024 * 1024,  # 50MB
        backupCount=5
    )
    file_handler.setFormatter(formatter)
    
    # Error file handler
    error_handler = logging.handlers.RotatingFileHandler(
        '/app/logs/error.log',
        maxBytes=25 * 1024 * 1024,  # 25MB
        backupCount=3
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper()),
        handlers=[console_handler, file_handler, error_handler],
        format='%(message)s'
    )
    
    # Set specific logger levels
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    logging.getLogger('aioredis').setLevel(logging.WARNING)
    logging.getLogger('uvicorn.access').setLevel(logging.INFO)


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Get a structured logger instance.
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        BoundLogger: Configured structlog logger
    """
    return structlog.get_logger(name)


def set_correlation_id(corr_id: Optional[str] = None) -> str:
    """
    Set correlation ID for request tracing.
    
    Args:
        corr_id: Correlation ID to set. If None, generates a new UUID.
        
    Returns:
        str: The correlation ID that was set
    """
    if corr_id is None:
        corr_id = str(uuid.uuid4())
    
    correlation_id.set(corr_id)
    return corr_id


def get_correlation_id() -> Optional[str]:
    """
    Get current correlation ID.
    
    Returns:
        Optional[str]: Current correlation ID or None
    """
    return correlation_id.get()


class DatabaseLogHandler:
    """Handler for database operation logging."""
    
    def __init__(self):
        self.logger = get_logger(__name__)
    
    async def log_query(self, operation: str, table: str, duration: float, **kwargs) -> None:
        """Log database query with performance metrics."""
        await self.logger.ainfo(
            "Database operation completed",
            operation=operation,
            table=table,
            duration_ms=round(duration * 1000, 2),
            **kwargs
        )
    
    async def log_transaction(self, operation: str, tables: list, duration: float, record_count: int = None, **kwargs) -> None:
        """Log database transaction with detailed metrics."""
        await self.logger.ainfo(
            "Database transaction completed",
            operation=operation,
            tables=tables,
            duration_ms=round(duration * 1000, 2),
            record_count=record_count,
            **kwargs
        )
    
    async def log_slow_query(self, operation: str, table: str, duration: float, query_params: dict = None, **kwargs) -> None:
        """Log slow database queries for performance monitoring."""
        await self.logger.awarning(
            "Slow database query detected",
            operation=operation,
            table=table,
            duration_ms=round(duration * 1000, 2),
            query_params=query_params,
            **kwargs
        )
    
    async def log_connection_event(self, event_type: str, pool_size: int = None, active_connections: int = None, **kwargs) -> None:
        """Log database connection pool events."""
        await self.logger.ainfo(
            "Database connection event",
            event_type=event_type,
            pool_size=pool_size,
            active_connections=active_connections,
            **kwargs
        )
    
    async def log_error(self, operation: str, error: Exception, **kwargs) -> None:
        """Log database error."""
        await self.logger.aerror(
            "Database operation failed",
            operation=operation,
            error=str(error),
            error_type=type(error).__name__,
            **kwargs
        )


class SecurityLogHandler:
    """Handler for security-related logging."""
    
    def __init__(self):
        self.logger = get_logger(__name__)
    
    async def log_auth_attempt(self, username: str, success: bool, ip_address: str, user_agent: str = None, **kwargs) -> None:
        """Log authentication attempt with detailed context."""
        await self.logger.ainfo(
            "Authentication attempt",
            username=username,
            success=success,
            ip_address=ip_address,
            user_agent=user_agent,
            **kwargs
        )
    
    async def log_session_event(self, event_type: str, user_id: str, session_id: str, ip_address: str, **kwargs) -> None:
        """Log session management events."""
        await self.logger.ainfo(
            "Session event",
            event_type=event_type,
            user_id=user_id,
            session_id=session_id,
            ip_address=ip_address,
            **kwargs
        )
    
    async def log_permission_check(self, user_id: str, resource: str, action: str, allowed: bool, rule_matched: str = None, **kwargs) -> None:
        """Log permission check with rule evaluation details."""
        await self.logger.ainfo(
            "Permission evaluation",
            user_id=user_id,
            resource=resource,
            action=action,
            allowed=allowed,
            rule_matched=rule_matched,
            **kwargs
        )
    
    async def log_rate_limit_event(self, user_id: str, endpoint: str, limit_exceeded: bool, current_count: int, limit: int, **kwargs) -> None:
        """Log rate limiting events."""
        level = "warning" if limit_exceeded else "info"
        log_func = self.logger.awarning if limit_exceeded else self.logger.ainfo
        
        await log_func(
            "Rate limit check",
            user_id=user_id,
            endpoint=endpoint,
            limit_exceeded=limit_exceeded,
            current_count=current_count,
            limit=limit,
            **kwargs
        )
    
    async def log_security_event(self, event_type: str, severity: str, user_id: str = None, ip_address: str = None, details: Dict[str, Any] = None) -> None:
        """Log security event with comprehensive context."""
        await self.logger.awarning(
            "Security event detected",
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            ip_address=ip_address,
            **(details or {})
        )


class FileOperationLogHandler:
    """Handler for file operation logging with security audit trails."""
    
    def __init__(self):
        self.logger = get_logger(__name__)
    
    async def log_file_upload(self, filename: str, file_size: int, mime_type: str, user_id: str, file_path: str, checksum: str = None, **kwargs) -> None:
        """Log file upload with security details."""
        await self.logger.ainfo(
            "File upload completed",
            operation="upload",
            filename=filename,
            file_size=file_size,
            mime_type=mime_type,
            user_id=user_id,
            file_path=file_path,
            checksum=checksum,
            **kwargs
        )
    
    async def log_file_access(self, filename: str, user_id: str, file_path: str, access_type: str = "read", **kwargs) -> None:
        """Log file access for security auditing."""
        await self.logger.ainfo(
            "File access",
            operation="access",
            filename=filename,
            user_id=user_id,
            file_path=file_path,
            access_type=access_type,
            **kwargs
        )
    
    async def log_file_deletion(self, filename: str, user_id: str, file_path: str, file_size: int = None, **kwargs) -> None:
        """Log file deletion with audit trail."""
        await self.logger.ainfo(
            "File deletion completed",
            operation="delete",
            filename=filename,
            user_id=user_id,
            file_path=file_path,
            file_size=file_size,
            **kwargs
        )
    
    async def log_file_move(self, filename: str, user_id: str, old_path: str, new_path: str, **kwargs) -> None:
        """Log file move operations."""
        await self.logger.ainfo(
            "File move completed",
            operation="move",
            filename=filename,
            user_id=user_id,
            old_path=old_path,
            new_path=new_path,
            **kwargs
        )
    
    async def log_malware_scan(self, filename: str, scan_result: dict, user_id: str, **kwargs) -> None:
        """Log malware scan results."""
        level = "warning" if not scan_result.get("is_safe", True) else "info"
        log_func = self.logger.awarning if not scan_result.get("is_safe", True) else self.logger.ainfo
        
        await log_func(
            "Malware scan completed",
            operation="malware_scan",
            filename=filename,
            user_id=user_id,
            is_safe=scan_result.get("is_safe", True),
            threats_found=scan_result.get("threats_found", []),
            scan_engine=scan_result.get("scan_engine", "unknown"),
            **kwargs
        )
    
    async def log_file_validation_error(self, filename: str, user_id: str, error_type: str, error_details: str, **kwargs) -> None:
        """Log file validation errors."""
        await self.logger.awarning(
            "File validation failed",
            operation="validation",
            filename=filename,
            user_id=user_id,
            error_type=error_type,
            error_details=error_details,
            **kwargs
        )


class ErrorLogHandler:
    """Handler for comprehensive error logging with stack traces and correlation IDs."""
    
    def __init__(self):
        self.logger = get_logger(__name__)
    
    async def log_application_error(self, error: Exception, context: dict = None, user_id: str = None, request_path: str = None, **kwargs) -> None:
        """Log application errors with full context and stack trace."""
        import traceback
        
        error_context = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "stack_trace": traceback.format_exc(),
            "user_id": user_id,
            "request_path": request_path,
            **(context or {}),
            **kwargs
        }
        
        await self.logger.aerror(
            "Application error occurred",
            **error_context
        )
    
    async def log_validation_error(self, field: str, value: any, error_message: str, user_id: str = None, **kwargs) -> None:
        """Log validation errors with field details."""
        await self.logger.awarning(
            "Validation error",
            error_type="validation",
            field=field,
            value=str(value)[:100] if value else None,  # Truncate long values
            error_message=error_message,
            user_id=user_id,
            **kwargs
        )
    
    async def log_business_logic_error(self, operation: str, error_message: str, context: dict = None, user_id: str = None, **kwargs) -> None:
        """Log business logic errors."""
        await self.logger.awarning(
            "Business logic error",
            error_type="business_logic",
            operation=operation,
            error_message=error_message,
            user_id=user_id,
            **(context or {}),
            **kwargs
        )
    
    async def log_external_service_error(self, service_name: str, operation: str, error: Exception, response_code: int = None, **kwargs) -> None:
        """Log errors from external service calls."""
        await self.logger.aerror(
            "External service error",
            error_type="external_service",
            service_name=service_name,
            operation=operation,
            error_message=str(error),
            response_code=response_code,
            **kwargs
        )
    
    async def log_performance_warning(self, operation: str, duration: float, threshold: float, context: dict = None, **kwargs) -> None:
        """Log performance warnings when operations exceed thresholds."""
        await self.logger.awarning(
            "Performance threshold exceeded",
            warning_type="performance",
            operation=operation,
            duration_ms=round(duration * 1000, 2),
            threshold_ms=round(threshold * 1000, 2),
            **(context or {}),
            **kwargs
        )