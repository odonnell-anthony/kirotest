"""
Authentication service for JWT-based authentication with Redis session management.
"""
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from aioredis import Redis

from app.core.config import settings
from app.core.redis import get_redis
from app.models.user import User, UserRole
from app.services.audit import AuditService

logger = logging.getLogger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthenticationError(Exception):
    """Authentication related errors."""
    pass


class AuthorizationError(Exception):
    """Authorization related errors."""
    pass


class TokenBlacklistError(Exception):
    """Token blacklist related errors."""
    pass


class AuthenticationService:
    """Service for handling authentication and JWT token management."""
    
    def __init__(self, db: AsyncSession, audit_service: Optional[AuditService] = None):
        self.db = db
        self.audit_service = audit_service or AuditService(db)
    
    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash a password using bcrypt.
        
        Args:
            password: Plain text password
            
        Returns:
            str: Hashed password
        """
        return pwd_context.hash(password)
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Verify a password against its hash.
        
        Args:
            plain_password: Plain text password
            hashed_password: Hashed password
            
        Returns:
            bool: True if password matches
        """
        return pwd_context.verify(plain_password, hashed_password)
    
    async def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """
        Authenticate user with username and password.
        
        Args:
            username: Username or email
            password: Plain text password
            
        Returns:
            User: Authenticated user or None if authentication fails
        """
        try:
            # Try to find user by username or email
            stmt = select(User).where(
                (User.username == username) | (User.email == username)
            )
            result = await self.db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                logger.warning(f"Authentication failed: User not found for username: {username}")
                return None
            
            if not user.is_active:
                logger.warning(f"Authentication failed: User account disabled for username: {username}")
                return None
            
            if not self.verify_password(password, user.password_hash):
                logger.warning(f"Authentication failed: Invalid password for username: {username}")
                await self.audit_service.log_authentication_failure(
                    username=username,
                    reason="invalid_password",
                    ip_address=None  # Will be set by middleware
                )
                return None
            
            # Update last login time
            user.last_login_at = datetime.utcnow()
            await self.db.commit()
            
            logger.info(f"User authenticated successfully: {username}")
            await self.audit_service.log_authentication_success(
                user_id=user.id,
                username=username,
                ip_address=None  # Will be set by middleware
            )
            
            return user
            
        except Exception as e:
            logger.error(f"Error during authentication for username {username}: {e}")
            await self.db.rollback()
            return None
    
    def create_access_token(self, user: User, expires_delta: Optional[timedelta] = None) -> str:
        """
        Create JWT access token for user.
        
        Args:
            user: User object
            expires_delta: Token expiration time
            
        Returns:
            str: JWT token
        """
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
        
        # Generate unique token ID for blacklisting
        token_id = str(uuid.uuid4())
        
        to_encode = {
            "sub": str(user.id),
            "username": user.username,
            "email": user.email,
            "role": user.role.value,
            "exp": expire,
            "iat": datetime.utcnow(),
            "jti": token_id,  # JWT ID for blacklisting
            "type": "access"
        }
        
        encoded_jwt = jwt.encode(
            to_encode, 
            settings.JWT_SECRET_KEY, 
            algorithm=settings.JWT_ALGORITHM
        )
        
        logger.info(f"Access token created for user: {user.username}")
        return encoded_jwt
    
    def create_refresh_token(self, user: User) -> str:
        """
        Create JWT refresh token for user.
        
        Args:
            user: User object
            
        Returns:
            str: JWT refresh token
        """
        expire = datetime.utcnow() + timedelta(days=7)  # Refresh tokens last 7 days
        token_id = str(uuid.uuid4())
        
        to_encode = {
            "sub": str(user.id),
            "username": user.username,
            "exp": expire,
            "iat": datetime.utcnow(),
            "jti": token_id,
            "type": "refresh"
        }
        
        encoded_jwt = jwt.encode(
            to_encode,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM
        )
        
        logger.info(f"Refresh token created for user: {user.username}")
        return encoded_jwt
    
    async def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify and decode JWT token.
        
        Args:
            token: JWT token string
            
        Returns:
            Dict: Token payload or None if invalid
            
        Raises:
            AuthenticationError: If token is invalid or expired
            TokenBlacklistError: If token is blacklisted
        """
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM]
            )
            
            # Check if token is blacklisted
            token_id = payload.get("jti")
            if token_id and await self.is_token_blacklisted(token_id):
                raise TokenBlacklistError("Token has been blacklisted")
            
            return payload
            
        except JWTError as e:
            logger.warning(f"JWT verification failed: {e}")
            raise AuthenticationError(f"Invalid token: {e}")
        except TokenBlacklistError:
            raise
        except Exception as e:
            logger.error(f"Error verifying token: {e}")
            raise AuthenticationError(f"Token verification error: {e}")
    
    async def get_current_user(self, token: str) -> Optional[User]:
        """
        Get current user from JWT token.
        
        Args:
            token: JWT token string
            
        Returns:
            User: Current user or None if token is invalid
            
        Raises:
            AuthenticationError: If token is invalid
            AuthorizationError: If user is not found or inactive
        """
        try:
            payload = await self.verify_token(token)
            user_id = payload.get("sub")
            
            if not user_id:
                raise AuthenticationError("Token missing user ID")
            
            # Get user from database
            stmt = select(User).where(User.id == uuid.UUID(user_id))
            result = await self.db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                raise AuthorizationError("User not found")
            
            if not user.is_active:
                raise AuthorizationError("User account is disabled")
            
            return user
            
        except (AuthenticationError, AuthorizationError):
            raise
        except Exception as e:
            logger.error(f"Error getting current user: {e}")
            raise AuthenticationError(f"Failed to get current user: {e}")
    
    async def blacklist_token(self, token: str) -> bool:
        """
        Add token to blacklist (for logout).
        
        Args:
            token: JWT token to blacklist
            
        Returns:
            bool: True if successfully blacklisted
        """
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
                options={"verify_exp": False}  # Allow expired tokens for blacklisting
            )
            
            token_id = payload.get("jti")
            if not token_id:
                logger.warning("Token missing JTI for blacklisting")
                return False
            
            # Calculate remaining TTL
            exp = payload.get("exp")
            if exp:
                expire_time = datetime.fromtimestamp(exp)
                ttl = max(0, int((expire_time - datetime.utcnow()).total_seconds()))
            else:
                ttl = settings.JWT_EXPIRE_MINUTES * 60  # Default TTL
            
            # Add to Redis blacklist with TTL
            redis = await get_redis()
            blacklist_key = f"blacklist:token:{token_id}"
            await redis.setex(blacklist_key, ttl, "blacklisted")
            
            logger.info(f"Token blacklisted: {token_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error blacklisting token: {e}")
            return False
    
    async def is_token_blacklisted(self, token_id: str) -> bool:
        """
        Check if token is blacklisted.
        
        Args:
            token_id: JWT token ID (jti claim)
            
        Returns:
            bool: True if token is blacklisted
        """
        try:
            redis = await get_redis()
            blacklist_key = f"blacklist:token:{token_id}"
            return await redis.exists(blacklist_key)
        except Exception as e:
            logger.error(f"Error checking token blacklist: {e}")
            return False
    
    async def refresh_access_token(self, refresh_token: str) -> Optional[str]:
        """
        Create new access token from refresh token.
        
        Args:
            refresh_token: Valid refresh token
            
        Returns:
            str: New access token or None if refresh token is invalid
            
        Raises:
            AuthenticationError: If refresh token is invalid
        """
        try:
            payload = await self.verify_token(refresh_token)
            
            # Verify it's a refresh token
            if payload.get("type") != "refresh":
                raise AuthenticationError("Invalid token type for refresh")
            
            user_id = payload.get("sub")
            if not user_id:
                raise AuthenticationError("Refresh token missing user ID")
            
            # Get user from database
            stmt = select(User).where(User.id == uuid.UUID(user_id))
            result = await self.db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user or not user.is_active:
                raise AuthenticationError("User not found or inactive")
            
            # Create new access token
            new_access_token = self.create_access_token(user)
            
            logger.info(f"Access token refreshed for user: {user.username}")
            return new_access_token
            
        except (AuthenticationError, TokenBlacklistError):
            raise
        except Exception as e:
            logger.error(f"Error refreshing token: {e}")
            raise AuthenticationError(f"Token refresh failed: {e}")
    
    async def create_user_session(self, user: User, ip_address: Optional[str] = None) -> Dict[str, str]:
        """
        Create user session with access and refresh tokens.
        
        Args:
            user: User object
            ip_address: Client IP address
            
        Returns:
            Dict: Dictionary containing access_token and refresh_token
        """
        try:
            access_token = self.create_access_token(user)
            refresh_token = self.create_refresh_token(user)
            
            # Store session info in Redis for tracking
            session_id = str(uuid.uuid4())
            session_data = {
                "user_id": str(user.id),
                "username": user.username,
                "ip_address": ip_address or "unknown",
                "created_at": datetime.utcnow().isoformat(),
                "last_activity": datetime.utcnow().isoformat()
            }
            
            redis = await get_redis()
            session_key = f"session:{session_id}"
            await redis.hset(session_key, mapping=session_data)
            await redis.expire(session_key, 7 * 24 * 60 * 60)  # 7 days
            
            logger.info(f"Session created for user: {user.username}")
            
            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": settings.JWT_EXPIRE_MINUTES * 60
            }
            
        except Exception as e:
            logger.error(f"Error creating user session: {e}")
            raise AuthenticationError(f"Failed to create session: {e}")
    
    async def invalidate_user_sessions(self, user_id: uuid.UUID) -> bool:
        """
        Invalidate all sessions for a user (useful for security incidents).
        
        Args:
            user_id: User ID
            
        Returns:
            bool: True if sessions were invalidated
        """
        try:
            redis = await get_redis()
            
            # Find all sessions for the user
            pattern = "session:*"
            sessions = []
            
            async for key in redis.scan_iter(match=pattern):
                session_data = await redis.hgetall(key)
                if session_data.get("user_id") == str(user_id):
                    sessions.append(key)
            
            # Delete all user sessions
            if sessions:
                await redis.delete(*sessions)
                logger.info(f"Invalidated {len(sessions)} sessions for user: {user_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error invalidating user sessions: {e}")
            return False