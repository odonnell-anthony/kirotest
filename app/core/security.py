"""
Security middleware and utilities for input validation and protection.
"""
import logging
import re
import hashlib
import magic
from typing import Optional, Dict, Any, List
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import bleach
from urllib.parse import unquote

logger = logging.getLogger(__name__)

# Allowed HTML tags and attributes for content sanitization
ALLOWED_TAGS = [
    'p', 'br', 'strong', 'em', 'u', 'i', 'b', 'code', 'pre', 'blockquote',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'a', 'img',
    'table', 'thead', 'tbody', 'tr', 'th', 'td', 'div', 'span'
]

ALLOWED_ATTRIBUTES = {
    'a': ['href', 'title'],
    'img': ['src', 'alt', 'title', 'width', 'height'],
    'div': ['class'],
    'span': ['class'],
    'code': ['class'],
    'pre': ['class']
}

# Allowed file types for uploads
ALLOWED_FILE_TYPES = {
    'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml',
    'text/plain', 'text/markdown', 'text/csv',
    'application/pdf', 'application/json', 'application/xml',
    'application/zip', 'application/x-zip-compressed'
}

# Maximum file size (100MB)
MAX_FILE_SIZE = 100 * 1024 * 1024

# Suspicious patterns for security scanning
SUSPICIOUS_PATTERNS = [
    r'<script[^>]*>.*?</script>',  # Script tags
    r'javascript:',  # JavaScript URLs
    r'on\w+\s*=',  # Event handlers
    r'eval\s*\(',  # eval() calls
    r'document\.',  # DOM access
    r'window\.',  # Window object access
    r'\.\./\.\.',  # Directory traversal
    r'union\s+select',  # SQL injection
    r'drop\s+table',  # SQL injection
    r'insert\s+into',  # SQL injection
    r'delete\s+from',  # SQL injection
]


class SecurityMiddleware(BaseHTTPMiddleware):
    """Security middleware for headers and basic protection."""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next):
        """Process request and add security headers."""
        try:
            # Check for suspicious patterns in URL
            if self._check_suspicious_url(str(request.url)):
                logger.warning(f"Suspicious URL detected: {request.url}")
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"error": "Invalid request"}
                )
            
            # Process the request
            response = await call_next(request)
            
            # Add security headers
            self._add_security_headers(response)
            
            return response
            
        except Exception as e:
            logger.error(f"Security middleware error: {e}")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"error": "Internal server error"}
            )
    
    def _check_suspicious_url(self, url: str) -> bool:
        """Check URL for suspicious patterns."""
        try:
            decoded_url = unquote(url)
            
            for pattern in SUSPICIOUS_PATTERNS:
                if re.search(pattern, decoded_url, re.IGNORECASE):
                    return True
            
            return False
            
        except Exception:
            return True  # Err on the side of caution
    
    def _add_security_headers(self, response: Response) -> None:
        """Add security headers to response."""
        # Content Security Policy
        csp_policy = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        response.headers["Content-Security-Policy"] = csp_policy
        
        # Other security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        
        # HSTS (only for HTTPS)
        if hasattr(response, 'headers') and response.headers.get('X-Forwarded-Proto') == 'https':
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"


class InputValidator:
    """Input validation and sanitization utilities."""
    
    @staticmethod
    def sanitize_html(content: str) -> str:
        """
        Sanitize HTML content to prevent XSS attacks.
        
        Args:
            content: HTML content to sanitize
            
        Returns:
            str: Sanitized HTML content
        """
        try:
            return bleach.clean(
                content,
                tags=ALLOWED_TAGS,
                attributes=ALLOWED_ATTRIBUTES,
                strip=True
            )
        except Exception as e:
            logger.error(f"Error sanitizing HTML: {e}")
            return bleach.clean(content, tags=[], attributes={}, strip=True)
    
    @staticmethod
    def sanitize_text(text: str) -> str:
        """
        Sanitize plain text input.
        
        Args:
            text: Text to sanitize
            
        Returns:
            str: Sanitized text
        """
        try:
            # Remove null bytes and control characters
            text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
            
            # Normalize whitespace
            text = re.sub(r'\s+', ' ', text).strip()
            
            return text
            
        except Exception as e:
            logger.error(f"Error sanitizing text: {e}")
            return ""
    
    @staticmethod
    def validate_file_type(file_content: bytes, filename: str) -> bool:
        """
        Validate file type using magic numbers.
        
        Args:
            file_content: File content bytes
            filename: Original filename
            
        Returns:
            bool: True if file type is allowed
        """
        try:
            # Check MIME type using python-magic
            mime_type = magic.from_buffer(file_content, mime=True)
            
            if mime_type not in ALLOWED_FILE_TYPES:
                logger.warning(f"Disallowed file type: {mime_type} for file {filename}")
                return False
            
            # Additional checks for specific file types
            if mime_type.startswith('image/'):
                return InputValidator._validate_image_file(file_content)
            elif mime_type == 'text/plain':
                return InputValidator._validate_text_file(file_content)
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating file type: {e}")
            return False
    
    @staticmethod
    def _validate_image_file(file_content: bytes) -> bool:
        """Validate image file content."""
        try:
            # Check for common image headers
            if file_content.startswith(b'\xFF\xD8\xFF'):  # JPEG
                return True
            elif file_content.startswith(b'\x89PNG\r\n\x1a\n'):  # PNG
                return True
            elif file_content.startswith(b'GIF8'):  # GIF
                return True
            elif file_content.startswith(b'RIFF') and b'WEBP' in file_content[:12]:  # WebP
                return True
            elif file_content.startswith(b'<svg') or file_content.startswith(b'<?xml'):  # SVG
                # Additional validation for SVG to prevent XSS
                content_str = file_content.decode('utf-8', errors='ignore')
                if re.search(r'<script[^>]*>', content_str, re.IGNORECASE):
                    return False
                if re.search(r'javascript:', content_str, re.IGNORECASE):
                    return False
                return True
            
            return False
            
        except Exception:
            return False
    
    @staticmethod
    def _validate_text_file(file_content: bytes) -> bool:
        """Validate text file content."""
        try:
            # Try to decode as UTF-8
            content_str = file_content.decode('utf-8')
            
            # Check for suspicious patterns
            for pattern in SUSPICIOUS_PATTERNS:
                if re.search(pattern, content_str, re.IGNORECASE):
                    return False
            
            return True
            
        except UnicodeDecodeError:
            return False
        except Exception:
            return False
    
    @staticmethod
    def validate_file_size(file_size: int) -> bool:
        """
        Validate file size.
        
        Args:
            file_size: File size in bytes
            
        Returns:
            bool: True if file size is within limits
        """
        return 0 < file_size <= MAX_FILE_SIZE
    
    @staticmethod
    def scan_for_malware(file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Basic malware scanning using pattern matching.
        
        Args:
            file_content: File content bytes
            filename: Original filename
            
        Returns:
            Dict: Scan result with is_safe boolean and details
        """
        try:
            scan_result = {
                "is_safe": True,
                "threats_found": [],
                "scan_time": None
            }
            
            # Convert to string for pattern matching (if possible)
            try:
                content_str = file_content.decode('utf-8', errors='ignore')
            except Exception:
                content_str = str(file_content)
            
            # Check for suspicious patterns
            threats = []
            for i, pattern in enumerate(SUSPICIOUS_PATTERNS):
                if re.search(pattern, content_str, re.IGNORECASE):
                    threats.append(f"Suspicious pattern {i+1} detected")
            
            # Check for executable file extensions
            dangerous_extensions = ['.exe', '.bat', '.cmd', '.scr', '.pif', '.com', '.vbs', '.js']
            if any(filename.lower().endswith(ext) for ext in dangerous_extensions):
                threats.append("Potentially dangerous file extension")
            
            # Check file size (extremely large files might be suspicious)
            if len(file_content) > MAX_FILE_SIZE:
                threats.append("File size exceeds maximum allowed")
            
            if threats:
                scan_result["is_safe"] = False
                scan_result["threats_found"] = threats
            
            return scan_result
            
        except Exception as e:
            logger.error(f"Error scanning file for malware: {e}")
            return {
                "is_safe": False,
                "threats_found": ["Scan error occurred"],
                "scan_time": None
            }
    
    @staticmethod
    def validate_path(path: str) -> bool:
        """
        Validate file/folder path to prevent directory traversal.
        
        Args:
            path: Path to validate
            
        Returns:
            bool: True if path is safe
        """
        try:
            # Normalize path
            normalized_path = path.replace('\\', '/').strip()
            
            # Check for directory traversal patterns
            if '..' in normalized_path:
                return False
            
            # Check for absolute paths (should be relative)
            if normalized_path.startswith('/'):
                # Allow paths starting with / for our API
                pass
            
            # Check for null bytes
            if '\x00' in normalized_path:
                return False
            
            # Check for valid characters
            if not re.match(r'^[/a-zA-Z0-9._\-\s]+$', normalized_path):
                return False
            
            return True
            
        except Exception:
            return False
    
    @staticmethod
    def generate_file_hash(file_content: bytes) -> str:
        """
        Generate SHA-256 hash of file content.
        
        Args:
            file_content: File content bytes
            
        Returns:
            str: SHA-256 hash
        """
        return hashlib.sha256(file_content).hexdigest()


class RateLimitService:
    """Rate limiting service using Redis."""
    
    def __init__(self):
        self.default_limits = {
            "login": {"requests": 5, "window": 300},  # 5 requests per 5 minutes
            "api": {"requests": 100, "window": 60},   # 100 requests per minute
            "upload": {"requests": 10, "window": 300}, # 10 uploads per 5 minutes
            "search": {"requests": 200, "window": 60}, # 200 searches per minute
        }
    
    async def check_rate_limit(
        self, 
        key: str, 
        limit_type: str = "api",
        custom_limit: Optional[Dict[str, int]] = None
    ) -> Dict[str, Any]:
        """
        Check if request is within rate limits.
        
        Args:
            key: Rate limit key (usually user ID or IP)
            limit_type: Type of rate limit to apply
            custom_limit: Custom limit override
            
        Returns:
            Dict: Rate limit status
        """
        try:
            from app.core.redis import get_redis
            
            redis = await get_redis()
            
            # Get limit configuration
            if custom_limit:
                limit_config = custom_limit
            else:
                limit_config = self.default_limits.get(limit_type, self.default_limits["api"])
            
            requests_limit = limit_config["requests"]
            window_seconds = limit_config["window"]
            
            # Create Redis key
            redis_key = f"rate_limit:{limit_type}:{key}"
            
            # Get current count
            current_count = await redis.get(redis_key)
            
            if current_count is None:
                # First request in window
                await redis.setex(redis_key, window_seconds, 1)
                return {
                    "allowed": True,
                    "requests_remaining": requests_limit - 1,
                    "reset_time": window_seconds
                }
            
            current_count = int(current_count)
            
            if current_count >= requests_limit:
                # Rate limit exceeded
                ttl = await redis.ttl(redis_key)
                return {
                    "allowed": False,
                    "requests_remaining": 0,
                    "reset_time": ttl if ttl > 0 else window_seconds
                }
            
            # Increment counter
            await redis.incr(redis_key)
            
            return {
                "allowed": True,
                "requests_remaining": requests_limit - current_count - 1,
                "reset_time": await redis.ttl(redis_key)
            }
            
        except Exception as e:
            logger.error(f"Rate limit check error: {e}")
            # Allow request on error to avoid blocking legitimate traffic
            return {
                "allowed": True,
                "requests_remaining": 0,
                "reset_time": 0
            }


# Global rate limit service instance
rate_limit_service = RateLimitService()