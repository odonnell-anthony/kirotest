"""
Authentication API endpoints.
"""
import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_user, get_auth_service, security
from app.core.rate_limit import login_rate_limit
from app.models.user import User
from app.services.auth import AuthenticationService, AuthenticationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    """Login request model."""
    username: str = Field(..., min_length=1, max_length=255, description="Username or email")
    password: str = Field(..., min_length=1, description="Password")


class LoginResponse(BaseModel):
    """Login response model."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Dict[str, Any]


class RefreshRequest(BaseModel):
    """Token refresh request model."""
    refresh_token: str = Field(..., description="Valid refresh token")


class RefreshResponse(BaseModel):
    """Token refresh response model."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserProfile(BaseModel):
    """User profile response model."""
    id: str
    username: str
    email: str
    role: str
    is_active: bool
    theme_preference: str
    created_at: str
    last_login_at: str = None


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str


@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    login_data: LoginRequest,
    auth_service: AuthenticationService = Depends(get_auth_service),
    _rate_limit: dict = Depends(login_rate_limit)
):
    """
    Authenticate user and return JWT tokens.
    
    Args:
        request: FastAPI request object
        login_data: Login credentials
        auth_service: Authentication service
        
    Returns:
        LoginResponse: JWT tokens and user info
        
    Raises:
        HTTPException: If authentication fails
    """
    try:
        # Authenticate user
        user = await auth_service.authenticate_user(
            username=login_data.username,
            password=login_data.password
        )
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )
        
        # Get client IP address
        client_ip = None
        if request.client:
            client_ip = request.client.host
        elif "x-forwarded-for" in request.headers:
            client_ip = request.headers["x-forwarded-for"].split(",")[0].strip()
        elif "x-real-ip" in request.headers:
            client_ip = request.headers["x-real-ip"]
        
        # Create session with tokens
        session_data = await auth_service.create_user_session(user, client_ip)
        
        # Prepare user data for response
        user_data = {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "role": user.role.value,
            "is_active": user.is_active,
            "theme_preference": user.theme_preference.value,
            "created_at": user.created_at.isoformat(),
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None
        }
        
        logger.info(f"User logged in successfully: {user.username}")
        
        return LoginResponse(
            access_token=session_data["access_token"],
            refresh_token=session_data["refresh_token"],
            token_type=session_data["token_type"],
            expires_in=session_data["expires_in"],
            user=user_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service error"
        )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth_service: AuthenticationService = Depends(get_auth_service)
):
    """
    Logout user by blacklisting the current token.
    
    Args:
        credentials: HTTP Bearer credentials
        auth_service: Authentication service
        
    Returns:
        MessageResponse: Logout confirmation
        
    Raises:
        HTTPException: If logout fails
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials required"
        )
    
    try:
        # Blacklist the current token
        success = await auth_service.blacklist_token(credentials.credentials)
        
        if not success:
            logger.warning("Failed to blacklist token during logout")
            # Don't fail the logout if blacklisting fails
        
        logger.info("User logged out successfully")
        return MessageResponse(message="Logged out successfully")
        
    except Exception as e:
        logger.error(f"Logout error: {e}")
        # Don't fail logout on errors
        return MessageResponse(message="Logged out successfully")


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(
    refresh_data: RefreshRequest,
    auth_service: AuthenticationService = Depends(get_auth_service)
):
    """
    Refresh access token using refresh token.
    
    Args:
        refresh_data: Refresh token data
        auth_service: Authentication service
        
    Returns:
        RefreshResponse: New access token
        
    Raises:
        HTTPException: If refresh fails
    """
    try:
        new_access_token = await auth_service.refresh_access_token(
            refresh_data.refresh_token
        )
        
        if not new_access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        logger.info("Access token refreshed successfully")
        
        return RefreshResponse(
            access_token=new_access_token,
            token_type="bearer",
            expires_in=30 * 60  # 30 minutes
        )
        
    except AuthenticationError as e:
        logger.warning(f"Token refresh failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh service error"
        )


@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user)
):
    """
    Get current user profile information.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        UserProfile: User profile data
    """
    return UserProfile(
        id=str(current_user.id),
        username=current_user.username,
        email=current_user.email,
        role=current_user.role.value,
        is_active=current_user.is_active,
        theme_preference=current_user.theme_preference.value,
        created_at=current_user.created_at.isoformat(),
        last_login_at=current_user.last_login_at.isoformat() if current_user.last_login_at else None
    )


@router.post("/validate", response_model=Dict[str, Any])
async def validate_token(
    current_user: User = Depends(get_current_user)
):
    """
    Validate current token and return user info.
    Useful for client-side token validation.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        Dict: Token validation result with user info
    """
    return {
        "valid": True,
        "user": {
            "id": str(current_user.id),
            "username": current_user.username,
            "email": current_user.email,
            "role": current_user.role.value,
            "is_active": current_user.is_active
        }
    }