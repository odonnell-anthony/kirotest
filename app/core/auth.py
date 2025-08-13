"""
Authentication dependencies and utilities for FastAPI.
"""
import logging
from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.models.permission import PermissionAction
from app.services.auth import AuthenticationService, AuthenticationError, AuthorizationError, TokenBlacklistError
from app.services.permission import PermissionService

logger = logging.getLogger(__name__)

# HTTP Bearer token scheme
security = HTTPBearer(auto_error=False)


async def get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthenticationService:
    """
    Dependency to get authentication service.
    
    Args:
        db: Database session
        
    Returns:
        AuthenticationService: Authentication service instance
    """
    return AuthenticationService(db)


async def get_permission_service(db: AsyncSession = Depends(get_db)) -> PermissionService:
    """
    Dependency to get permission service.
    
    Args:
        db: Database session
        
    Returns:
        PermissionService: Permission service instance
    """
    return PermissionService(db)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    auth_service: AuthenticationService = Depends(get_auth_service)
) -> User:
    """
    Dependency to get current authenticated user.
    
    Args:
        request: FastAPI request object
        credentials: HTTP Bearer credentials
        auth_service: Authentication service
        
    Returns:
        User: Current authenticated user
        
    Raises:
        HTTPException: If authentication fails
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        user = await auth_service.get_current_user(credentials.credentials)
        
        # Log the request for audit purposes
        logger.info(
            f"Authenticated request: user={user.username}, "
            f"endpoint={request.url.path}, method={request.method}, "
            f"ip={request.client.host if request.client else 'unknown'}"
        )
        
        return user
        
    except TokenBlacklistError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except AuthenticationError as e:
        logger.warning(f"Authentication failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except AuthorizationError as e:
        logger.warning(f"Authorization failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled or not found",
        )
    except Exception as e:
        logger.error(f"Unexpected error in authentication: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service error",
        )


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency to get current active user.
    
    Args:
        current_user: Current user from get_current_user
        
    Returns:
        User: Current active user
        
    Raises:
        HTTPException: If user is inactive
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )
    return current_user


async def get_current_admin_user(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """
    Dependency to get current admin user.
    
    Args:
        current_user: Current active user
        
    Returns:
        User: Current admin user
        
    Raises:
        HTTPException: If user is not admin
    """
    if current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user


async def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    auth_service: AuthenticationService = Depends(get_auth_service)
) -> Optional[User]:
    """
    Dependency to get current user if authenticated, None otherwise.
    Useful for endpoints that work for both authenticated and anonymous users.
    
    Args:
        credentials: HTTP Bearer credentials
        auth_service: Authentication service
        
    Returns:
        User: Current user or None if not authenticated
    """
    if not credentials:
        return None
    
    try:
        return await auth_service.get_current_user(credentials.credentials)
    except (AuthenticationError, AuthorizationError, TokenBlacklistError):
        return None
    except Exception as e:
        logger.error(f"Error in optional authentication: {e}")
        return None


# Alias for compatibility
get_current_user_optional = get_optional_current_user


class RequirePermissions:
    """
    Dependency class to require specific permissions.
    Usage: Depends(RequirePermissions([PermissionAction.READ_PAGES, PermissionAction.EDIT_PAGES]))
    """
    
    def __init__(self, required_permissions: list[PermissionAction], resource_path: str = "/"):
        self.required_permissions = required_permissions
        self.resource_path = resource_path
    
    async def __call__(
        self,
        request: Request,
        current_user: User = Depends(get_current_active_user),
        permission_service: PermissionService = Depends(get_permission_service)
    ) -> User:
        """
        Check if current user has required permissions.
        
        Args:
            request: FastAPI request object
            current_user: Current active user
            permission_service: Permission service
            
        Returns:
            User: Current user if permissions are satisfied
            
        Raises:
            HTTPException: If user lacks required permissions
        """
        # Get client IP for audit logging
        client_ip = None
        if request.client:
            client_ip = request.client.host
        elif "x-forwarded-for" in request.headers:
            client_ip = request.headers["x-forwarded-for"].split(",")[0].strip()
        elif "x-real-ip" in request.headers:
            client_ip = request.headers["x-real-ip"]
        
        # Check each required permission
        for permission in self.required_permissions:
            has_permission = await permission_service.check_permission(
                user=current_user,
                resource_path=self.resource_path,
                action=permission,
                ip_address=client_ip
            )
            
            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission '{permission.value}' required for resource '{self.resource_path}'"
                )
        
        return current_user


class RequireResourcePermission:
    """
    Dependency class to require permission for a specific resource path.
    Usage: Depends(RequireResourcePermission(PermissionAction.READ_PAGES))
    """
    
    def __init__(self, required_action: PermissionAction):
        self.required_action = required_action
    
    async def __call__(
        self,
        request: Request,
        resource_path: str,
        current_user: User = Depends(get_current_active_user),
        permission_service: PermissionService = Depends(get_permission_service)
    ) -> User:
        """
        Check if current user has permission for specific resource.
        
        Args:
            request: FastAPI request object
            resource_path: Resource path to check
            current_user: Current active user
            permission_service: Permission service
            
        Returns:
            User: Current user if permission is granted
            
        Raises:
            HTTPException: If user lacks required permission
        """
        # Get client IP for audit logging
        client_ip = None
        if request.client:
            client_ip = request.client.host
        elif "x-forwarded-for" in request.headers:
            client_ip = request.headers["x-forwarded-for"].split(",")[0].strip()
        elif "x-real-ip" in request.headers:
            client_ip = request.headers["x-real-ip"]
        
        has_permission = await permission_service.check_permission(
            user=current_user,
            resource_path=resource_path,
            action=self.required_action,
            ip_address=client_ip
        )
        
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{self.required_action.value}' required for resource '{resource_path}'"
            )
        
        return current_user