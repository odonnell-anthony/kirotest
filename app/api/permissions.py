"""
Permission management API endpoints.
"""
import logging
import uuid
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_admin_user, get_permission_service
from app.models.user import User
from app.models.permission import PermissionAction, PermissionEffect, PermissionGroup, Permission
from app.services.permission import PermissionService, PermissionError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/permissions", tags=["permissions"])


class PermissionGroupCreate(BaseModel):
    """Permission group creation model."""
    name: str = Field(..., min_length=1, max_length=100, description="Group name")
    description: Optional[str] = Field(None, max_length=500, description="Group description")


class PermissionGroupResponse(BaseModel):
    """Permission group response model."""
    id: str
    name: str
    description: Optional[str]
    created_at: str
    permissions_count: int


class PermissionCreate(BaseModel):
    """Permission creation model."""
    group_id: str = Field(..., description="Permission group ID")
    resource_pattern: str = Field(..., min_length=1, description="Resource path pattern")
    action: PermissionAction = Field(..., description="Permission action")
    effect: PermissionEffect = Field(..., description="Permission effect")


class PermissionResponse(BaseModel):
    """Permission response model."""
    id: str
    group_id: str
    group_name: str
    resource_pattern: str
    action: str
    effect: str
    created_at: str


class UserGroupAssignment(BaseModel):
    """User group assignment model."""
    user_id: str = Field(..., description="User ID")
    group_id: str = Field(..., description="Permission group ID")


class UserPermissionsResponse(BaseModel):
    """User permissions response model."""
    user_id: str
    username: str
    groups: List[Dict[str, Any]]
    effective_permissions: Dict[str, bool]


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str


@router.post("/groups", response_model=PermissionGroupResponse)
async def create_permission_group(
    group_data: PermissionGroupCreate,
    current_user: User = Depends(get_current_admin_user),
    permission_service: PermissionService = Depends(get_permission_service)
):
    """
    Create a new permission group.
    
    Args:
        group_data: Permission group data
        current_user: Current admin user
        permission_service: Permission service
        
    Returns:
        PermissionGroupResponse: Created permission group
        
    Raises:
        HTTPException: If creation fails
    """
    try:
        group = await permission_service.create_permission_group(
            name=group_data.name,
            description=group_data.description
        )
        
        logger.info(f"Permission group created by {current_user.username}: {group.name}")
        
        return PermissionGroupResponse(
            id=str(group.id),
            name=group.name,
            description=group.description,
            created_at=group.created_at.isoformat(),
            permissions_count=0
        )
        
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating permission group: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create permission group"
        )


@router.get("/groups", response_model=List[PermissionGroupResponse])
async def list_permission_groups(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List all permission groups.
    
    Args:
        current_user: Current admin user
        db: Database session
        
    Returns:
        List[PermissionGroupResponse]: List of permission groups
    """
    try:
        from sqlalchemy import select, func
        from sqlalchemy.orm import selectinload
        
        # Query groups with permission counts
        stmt = (
            select(PermissionGroup, func.count(Permission.id).label('permissions_count'))
            .outerjoin(Permission)
            .group_by(PermissionGroup.id)
            .order_by(PermissionGroup.name)
        )
        
        result = await db.execute(stmt)
        groups_with_counts = result.all()
        
        return [
            PermissionGroupResponse(
                id=str(group.id),
                name=group.name,
                description=group.description,
                created_at=group.created_at.isoformat(),
                permissions_count=count
            )
            for group, count in groups_with_counts
        ]
        
    except Exception as e:
        logger.error(f"Error listing permission groups: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list permission groups"
        )


@router.post("/rules", response_model=PermissionResponse)
async def create_permission(
    permission_data: PermissionCreate,
    current_user: User = Depends(get_current_admin_user),
    permission_service: PermissionService = Depends(get_permission_service)
):
    """
    Create a new permission rule.
    
    Args:
        permission_data: Permission data
        current_user: Current admin user
        permission_service: Permission service
        
    Returns:
        PermissionResponse: Created permission
        
    Raises:
        HTTPException: If creation fails
    """
    try:
        permission = await permission_service.create_permission(
            group_id=uuid.UUID(permission_data.group_id),
            resource_pattern=permission_data.resource_pattern,
            action=permission_data.action,
            effect=permission_data.effect
        )
        
        # Get group name for response
        from sqlalchemy import select
        stmt = select(PermissionGroup).where(PermissionGroup.id == permission.group_id)
        result = await permission_service.db.execute(stmt)
        group = result.scalar_one()
        
        logger.info(f"Permission created by {current_user.username}: {permission_data.resource_pattern}")
        
        return PermissionResponse(
            id=str(permission.id),
            group_id=str(permission.group_id),
            group_name=group.name,
            resource_pattern=permission.resource_pattern,
            action=permission.action.value,
            effect=permission.effect.value,
            created_at=permission.created_at.isoformat()
        )
        
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid UUID format"
        )
    except Exception as e:
        logger.error(f"Error creating permission: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create permission"
        )


@router.get("/rules", response_model=List[PermissionResponse])
async def list_permissions(
    group_id: Optional[str] = None,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List permission rules, optionally filtered by group.
    
    Args:
        group_id: Optional group ID to filter by
        current_user: Current admin user
        db: Database session
        
    Returns:
        List[PermissionResponse]: List of permissions
    """
    try:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        
        stmt = (
            select(Permission)
            .options(selectinload(Permission.group))
            .order_by(Permission.resource_pattern)
        )
        
        if group_id:
            stmt = stmt.where(Permission.group_id == uuid.UUID(group_id))
        
        result = await db.execute(stmt)
        permissions = result.scalars().all()
        
        return [
            PermissionResponse(
                id=str(permission.id),
                group_id=str(permission.group_id),
                group_name=permission.group.name,
                resource_pattern=permission.resource_pattern,
                action=permission.action.value,
                effect=permission.effect.value,
                created_at=permission.created_at.isoformat()
            )
            for permission in permissions
        ]
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid UUID format"
        )
    except Exception as e:
        logger.error(f"Error listing permissions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list permissions"
        )


@router.post("/assign", response_model=MessageResponse)
async def assign_user_to_group(
    assignment: UserGroupAssignment,
    current_user: User = Depends(get_current_admin_user),
    permission_service: PermissionService = Depends(get_permission_service)
):
    """
    Assign user to permission group.
    
    Args:
        assignment: User group assignment data
        current_user: Current admin user
        permission_service: Permission service
        
    Returns:
        MessageResponse: Assignment confirmation
        
    Raises:
        HTTPException: If assignment fails
    """
    try:
        await permission_service.assign_user_to_group(
            user_id=uuid.UUID(assignment.user_id),
            group_id=uuid.UUID(assignment.group_id)
        )
        
        logger.info(f"User assigned to group by {current_user.username}: {assignment.user_id} -> {assignment.group_id}")
        
        return MessageResponse(message="User assigned to group successfully")
        
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid UUID format"
        )
    except Exception as e:
        logger.error(f"Error assigning user to group: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to assign user to group"
        )


@router.delete("/assign", response_model=MessageResponse)
async def remove_user_from_group(
    assignment: UserGroupAssignment,
    current_user: User = Depends(get_current_admin_user),
    permission_service: PermissionService = Depends(get_permission_service)
):
    """
    Remove user from permission group.
    
    Args:
        assignment: User group assignment data
        current_user: Current admin user
        permission_service: Permission service
        
    Returns:
        MessageResponse: Removal confirmation
        
    Raises:
        HTTPException: If removal fails
    """
    try:
        success = await permission_service.remove_user_from_group(
            user_id=uuid.UUID(assignment.user_id),
            group_id=uuid.UUID(assignment.group_id)
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User group assignment not found"
            )
        
        logger.info(f"User removed from group by {current_user.username}: {assignment.user_id} -> {assignment.group_id}")
        
        return MessageResponse(message="User removed from group successfully")
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid UUID format"
        )
    except Exception as e:
        logger.error(f"Error removing user from group: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove user from group"
        )


@router.get("/users/{user_id}", response_model=UserPermissionsResponse)
async def get_user_permissions(
    user_id: str,
    resource_path: str = "/",
    current_user: User = Depends(get_current_admin_user),
    permission_service: PermissionService = Depends(get_permission_service),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user's permissions and group memberships.
    
    Args:
        user_id: User ID
        resource_path: Resource path to check permissions for
        current_user: Current admin user
        permission_service: Permission service
        db: Database session
        
    Returns:
        UserPermissionsResponse: User permissions data
        
    Raises:
        HTTPException: If user not found or error occurs
    """
    try:
        from sqlalchemy import select
        
        # Get user
        user_stmt = select(User).where(User.id == uuid.UUID(user_id))
        user_result = await db.execute(user_stmt)
        user = user_result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Get user's groups
        groups = await permission_service.get_user_groups(user.id)
        
        # Get effective permissions for the resource path
        effective_permissions = await permission_service.get_effective_permissions(
            user=user,
            resource_path=resource_path
        )
        
        groups_data = [
            {
                "id": str(group.id),
                "name": group.name,
                "description": group.description,
                "permissions_count": len(group.permissions)
            }
            for group in groups
        ]
        
        return UserPermissionsResponse(
            user_id=str(user.id),
            username=user.username,
            groups=groups_data,
            effective_permissions=effective_permissions
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid UUID format"
        )
    except Exception as e:
        logger.error(f"Error getting user permissions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user permissions"
        )


@router.post("/check", response_model=Dict[str, bool])
async def check_permission(
    request: Request,
    resource_path: str,
    action: PermissionAction,
    current_user: User = Depends(get_current_admin_user),
    permission_service: PermissionService = Depends(get_permission_service)
):
    """
    Check if current user has specific permission.
    
    Args:
        request: FastAPI request object
        resource_path: Resource path to check
        action: Permission action to check
        current_user: Current admin user
        permission_service: Permission service
        
    Returns:
        Dict[str, bool]: Permission check result
    """
    try:
        # Get client IP
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
            action=action,
            ip_address=client_ip
        )
        
        return {
            "allowed": has_permission,
            "resource_path": resource_path,
            "action": action.value,
            "user_id": str(current_user.id)
        }
        
    except Exception as e:
        logger.error(f"Error checking permission: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check permission"
        )