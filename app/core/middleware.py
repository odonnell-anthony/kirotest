"""
Middleware for comprehensive request/response logging and monitoring.
"""
import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import StreamingResponse
import structlog

from app.core.logging import set_correlation_id, get_logger

logger = get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for comprehensive HTTP request/response logging."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and log comprehensive details."""
        # Set correlation ID for request tracing
        correlation_id = str(uuid.uuid4())
        set_correlation_id(correlation_id)
        
        # Extract request details
        start_time = time.time()
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "")
        method = request.method
        url = str(request.url)
        path = request.url.path
        query_params = dict(request.query_params)
        
        # Log request start
        await logger.ainfo(
            "HTTP request started",
            method=method,
            path=path,
            url=url,
            client_ip=client_ip,
            user_agent=user_agent,
            query_params=query_params,
            correlation_id=correlation_id
        )
        
        try:
            # Process request
            response = await call_next(request)
            
            # Calculate duration
            duration = time.time() - start_time
            
            # Extract response details
            status_code = response.status_code
            response_size = None
            
            # Get response size if available
            if hasattr(response, 'headers') and 'content-length' in response.headers:
                response_size = int(response.headers['content-length'])
            
            # Log successful request completion
            await logger.ainfo(
                "HTTP request completed",
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=round(duration * 1000, 2),
                response_size=response_size,
                client_ip=client_ip,
                correlation_id=correlation_id
            )
            
            # Log slow requests
            if duration > 1.0:  # Log requests taking more than 1 second
                await logger.awarning(
                    "Slow HTTP request detected",
                    method=method,
                    path=path,
                    duration_ms=round(duration * 1000, 2),
                    status_code=status_code,
                    client_ip=client_ip,
                    correlation_id=correlation_id
                )
            
            return response
            
        except Exception as e:
            # Calculate duration for failed requests
            duration = time.time() - start_time
            
            # Log request failure
            await logger.aerror(
                "HTTP request failed",
                method=method,
                path=path,
                duration_ms=round(duration * 1000, 2),
                error=str(e),
                error_type=type(e).__name__,
                client_ip=client_ip,
                correlation_id=correlation_id
            )
            
            raise
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request headers."""
        # Check for forwarded headers (common in load balancer setups)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # Take the first IP in the chain
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        # Fallback to direct client IP
        if hasattr(request, 'client') and request.client:
            return request.client.host
        
        return "unknown"


class DatabaseLoggingMiddleware:
    """Middleware for database operation logging."""
    
    def __init__(self):
        self.logger = get_logger(__name__)
    
    async def log_before_execute(self, conn, clauseelement, multiparams, params, execution_options):
        """Log before SQL execution."""
        # Store start time for duration calculation
        conn.info.setdefault('query_start_time', time.time())
        
        # Log query start (only for complex queries to avoid spam)
        if hasattr(clauseelement, 'table') and clauseelement.table is not None:
            table_name = str(clauseelement.table.name)
            operation = self._get_operation_type(str(clauseelement))
            
            await self.logger.adebug(
                "Database query started",
                operation=operation,
                table=table_name,
                correlation_id=get_correlation_id()
            )
    
    async def log_after_execute(self, conn, clauseelement, multiparams, params, execution_options, result):
        """Log after SQL execution."""
        start_time = conn.info.get('query_start_time')
        if start_time:
            duration = time.time() - start_time
            
            # Extract query details
            if hasattr(clauseelement, 'table') and clauseelement.table is not None:
                table_name = str(clauseelement.table.name)
                operation = self._get_operation_type(str(clauseelement))
                
                # Get row count if available
                row_count = None
                if hasattr(result, 'rowcount') and result.rowcount >= 0:
                    row_count = result.rowcount
                
                # Log query completion
                await self.logger.ainfo(
                    "Database query completed",
                    operation=operation,
                    table=table_name,
                    duration_ms=round(duration * 1000, 2),
                    row_count=row_count,
                    correlation_id=get_correlation_id()
                )
                
                # Log slow queries
                if duration > 0.5:  # Log queries taking more than 500ms
                    await self.logger.awarning(
                        "Slow database query detected",
                        operation=operation,
                        table=table_name,
                        duration_ms=round(duration * 1000, 2),
                        row_count=row_count,
                        correlation_id=get_correlation_id()
                    )
            
            # Clean up
            conn.info.pop('query_start_time', None)
    
    async def log_handle_error(self, exception_context):
        """Log database errors."""
        await self.logger.aerror(
            "Database error occurred",
            error=str(exception_context.original_exception),
            error_type=type(exception_context.original_exception).__name__,
            statement=str(exception_context.statement)[:500],  # Truncate long statements
            correlation_id=get_correlation_id()
        )
    
    def _get_operation_type(self, statement: str) -> str:
        """Extract operation type from SQL statement."""
        statement_lower = statement.lower().strip()
        
        if statement_lower.startswith('select'):
            return 'SELECT'
        elif statement_lower.startswith('insert'):
            return 'INSERT'
        elif statement_lower.startswith('update'):
            return 'UPDATE'
        elif statement_lower.startswith('delete'):
            return 'DELETE'
        elif statement_lower.startswith('create'):
            return 'CREATE'
        elif statement_lower.startswith('alter'):
            return 'ALTER'
        elif statement_lower.startswith('drop'):
            return 'DROP'
        else:
            return 'OTHER'


class SecurityLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for security event logging."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Monitor requests for security events."""
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "")
        path = request.url.path
        
        # Check for suspicious patterns
        await self._check_suspicious_patterns(request, client_ip, user_agent, path)
        
        # Process request
        response = await call_next(request)
        
        # Log security-relevant responses
        if response.status_code in [401, 403, 429]:
            await logger.awarning(
                "Security-relevant HTTP response",
                status_code=response.status_code,
                path=path,
                client_ip=client_ip,
                user_agent=user_agent,
                correlation_id=get_correlation_id()
            )
        
        return response
    
    async def _check_suspicious_patterns(self, request: Request, client_ip: str, user_agent: str, path: str):
        """Check for suspicious request patterns."""
        # Check for common attack patterns in path
        suspicious_patterns = [
            '../', '..\\', '/etc/passwd', '/proc/', 'cmd.exe', 'powershell',
            '<script', 'javascript:', 'vbscript:', 'onload=', 'onerror=',
            'union select', 'drop table', 'insert into', 'delete from',
            '1=1', '1\'=\'1', 'admin\'--', '\' or \'1\'=\'1'
        ]
        
        path_lower = path.lower()
        for pattern in suspicious_patterns:
            if pattern in path_lower:
                await logger.awarning(
                    "Suspicious request pattern detected",
                    pattern=pattern,
                    path=path,
                    client_ip=client_ip,
                    user_agent=user_agent,
                    correlation_id=get_correlation_id()
                )
                break
        
        # Check for suspicious user agents
        suspicious_user_agents = [
            'sqlmap', 'nikto', 'nmap', 'masscan', 'nessus', 'openvas',
            'burpsuite', 'owasp zap', 'w3af', 'skipfish'
        ]
        
        user_agent_lower = user_agent.lower()
        for suspicious_ua in suspicious_user_agents:
            if suspicious_ua in user_agent_lower:
                await logger.awarning(
                    "Suspicious user agent detected",
                    user_agent=user_agent,
                    path=path,
                    client_ip=client_ip,
                    correlation_id=get_correlation_id()
                )
                break
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request headers."""
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        if hasattr(request, 'client') and request.client:
            return request.client.host
        
        return "unknown"