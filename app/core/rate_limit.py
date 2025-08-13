"""
Rate limiting middleware and decorators.
"""
import logging
from typing import Optional, Dict, Any, Callable
from functools import wraps
from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.security import rate_limit_service
from app.models.user import User

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Global rate limiting middleware."""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.exempt_paths = ["/api/v1/health", "/api/docs", "/api/redoc"]
    
    async def dispatch(self, request: Request, call_next):
        """Apply rate limiting to requests."""
        try:
            # Skip rate limiting for exempt paths
            if any(request.url.path.startswith(path) for path in self.exempt_paths):
                return await call_next(request)
            
            # Get client identifier
            client_id = self._get_client_id(request)
            
            # Check rate limit
            rate_limit_result = await rate_limit_service.check_rate_limit(
                key=client_id,
                limit_type="api"
            )
            
            if not rate_limit_result["allowed"]:
                logger.warning(f"Rate limit exceeded for client: {client_id}")
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": "Rate limit exceeded",
                        "detail": "Too many requests. Please try again later.",
                        "reset_time": rate_limit_result["reset_time"]
                    },
                    headers={
                        "X-RateLimit-Limit": "100",
                        "X-RateLimit-Remaining": str(rate_limit_result["requests_remaining"]),
                        "X-RateLimit-Reset": str(rate_limit_result["reset_time"]),
                        "Retry-After": str(rate_limit_result["reset_time"])
                    }
                )
            
            # Process request
            response = await call_next(request)
            
            # Add rate limit headers to response
            response.headers["X-RateLimit-Limit"] = "100"
            response.headers["X-RateLimit-Remaining"] = str(rate_limit_result["requests_remaining"])
            response.headers["X-RateLimit-Reset"] = str(rate_limit_result["reset_time"])
            
            return response
            
        except Exception as e:
            logger.error(f"Rate limit middleware error: {e}")
            # Continue processing on error
            return await call_next(request)
    
    def _get_client_id(self, request: Request) -> str:
        """Get client identifier for rate limiting."""
        # Try to get user ID from token if available
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                from jose import jwt
                from app.core.config import settings
                
                token = auth_header.split(" ")[1]
                payload = jwt.decode(
                    token,
                    settings.JWT_SECRET_KEY,
                    algorithms=[settings.JWT_ALGORITHM],
                    options={"verify_exp": False}  # Don't verify expiration for rate limiting
                )
                user_id = payload.get("sub")
                if user_id:
                    return f"user:{user_id}"
            except Exception:
                pass
        
        # Fall back to IP address
        client_ip = request.client.host if request.client else "unknown"
        
        # Check for forwarded IP headers
        if "x-forwarded-for" in request.headers:
            client_ip = request.headers["x-forwarded-for"].split(",")[0].strip()
        elif "x-real-ip" in request.headers:
            client_ip = request.headers["x-real-ip"]
        
        return f"ip:{client_ip}"


def rate_limit(
    limit_type: str = "api",
    requests: Optional[int] = None,
    window: Optional[int] = None
):
    """
    Decorator for endpoint-specific rate limiting.
    
    Args:
        limit_type: Type of rate limit
        requests: Number of requests allowed (overrides default)
        window: Time window in seconds (overrides default)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request from args/kwargs
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if not request:
                # Look in kwargs
                request = kwargs.get('request')
            
            if not request:
                logger.warning("Rate limit decorator: Request object not found")
                return await func(*args, **kwargs)
            
            # Get client identifier
            client_id = _get_client_id_from_request(request)
            
            # Custom limit configuration
            custom_limit = None
            if requests is not None and window is not None:
                custom_limit = {"requests": requests, "window": window}
            
            # Check rate limit
            rate_limit_result = await rate_limit_service.check_rate_limit(
                key=client_id,
                limit_type=limit_type,
                custom_limit=custom_limit
            )
            
            if not rate_limit_result["allowed"]:
                logger.warning(f"Rate limit exceeded for {limit_type}: {client_id}")
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded for {limit_type}. Please try again later.",
                    headers={
                        "X-RateLimit-Limit": str(requests or 100),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(rate_limit_result["reset_time"]),
                        "Retry-After": str(rate_limit_result["reset_time"])
                    }
                )
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def user_rate_limit(
    limit_type: str = "api",
    requests: Optional[int] = None,
    window: Optional[int] = None
):
    """
    Decorator for user-specific rate limiting (requires authenticated user).
    
    Args:
        limit_type: Type of rate limit
        requests: Number of requests allowed (overrides default)
        window: Time window in seconds (overrides default)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract user from args/kwargs
            current_user = None
            for arg in args:
                if isinstance(arg, User):
                    current_user = arg
                    break
            
            if not current_user:
                # Look in kwargs
                current_user = kwargs.get('current_user')
            
            if not current_user:
                logger.warning("User rate limit decorator: User object not found")
                return await func(*args, **kwargs)
            
            # Use user ID as key
            client_id = f"user:{current_user.id}"
            
            # Custom limit configuration
            custom_limit = None
            if requests is not None and window is not None:
                custom_limit = {"requests": requests, "window": window}
            
            # Check rate limit
            rate_limit_result = await rate_limit_service.check_rate_limit(
                key=client_id,
                limit_type=limit_type,
                custom_limit=custom_limit
            )
            
            if not rate_limit_result["allowed"]:
                logger.warning(f"User rate limit exceeded for {limit_type}: {current_user.username}")
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded for {limit_type}. Please try again later.",
                    headers={
                        "X-RateLimit-Limit": str(requests or 100),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(rate_limit_result["reset_time"]),
                        "Retry-After": str(rate_limit_result["reset_time"])
                    }
                )
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


async def check_rate_limit_dependency(
    request: Request,
    limit_type: str = "api",
    custom_requests: Optional[int] = None,
    custom_window: Optional[int] = None
) -> Dict[str, Any]:
    """
    FastAPI dependency for rate limiting.
    
    Args:
        request: FastAPI request object
        limit_type: Type of rate limit
        custom_requests: Custom request limit
        custom_window: Custom time window
        
    Returns:
        Dict: Rate limit status
        
    Raises:
        HTTPException: If rate limit is exceeded
    """
    client_id = _get_client_id_from_request(request)
    
    custom_limit = None
    if custom_requests is not None and custom_window is not None:
        custom_limit = {"requests": custom_requests, "window": custom_window}
    
    rate_limit_result = await rate_limit_service.check_rate_limit(
        key=client_id,
        limit_type=limit_type,
        custom_limit=custom_limit
    )
    
    if not rate_limit_result["allowed"]:
        logger.warning(f"Rate limit exceeded for {limit_type}: {client_id}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded for {limit_type}. Please try again later.",
            headers={
                "X-RateLimit-Limit": str(custom_requests or 100),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(rate_limit_result["reset_time"]),
                "Retry-After": str(rate_limit_result["reset_time"])
            }
        )
    
    return rate_limit_result


def _get_client_id_from_request(request: Request) -> str:
    """Helper function to get client ID from request."""
    # Try to get user ID from token if available
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            from jose import jwt
            from app.core.config import settings
            
            token = auth_header.split(" ")[1]
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
                options={"verify_exp": False}
            )
            user_id = payload.get("sub")
            if user_id:
                return f"user:{user_id}"
        except Exception:
            pass
    
    # Fall back to IP address
    client_ip = request.client.host if request.client else "unknown"
    
    # Check for forwarded IP headers
    if "x-forwarded-for" in request.headers:
        client_ip = request.headers["x-forwarded-for"].split(",")[0].strip()
    elif "x-real-ip" in request.headers:
        client_ip = request.headers["x-real-ip"]
    
    return f"ip:{client_ip}"


# Specific rate limit dependencies for common use cases
async def login_rate_limit(request: Request) -> Dict[str, Any]:
    """Rate limit for login attempts."""
    return await check_rate_limit_dependency(
        request, 
        limit_type="login",
        custom_requests=5,
        custom_window=300
    )


async def upload_rate_limit(request: Request) -> Dict[str, Any]:
    """Rate limit for file uploads."""
    return await check_rate_limit_dependency(
        request,
        limit_type="upload", 
        custom_requests=10,
        custom_window=300
    )


async def search_rate_limit(request: Request) -> Dict[str, Any]:
    """Rate limit for search requests."""
    return await check_rate_limit_dependency(
        request,
        limit_type="search",
        custom_requests=200,
        custom_window=60
    )