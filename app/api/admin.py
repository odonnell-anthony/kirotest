"""
Admin API endpoints for user and system management.
"""
import uuid
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User, UserRole
from app.models.document import Document
from app.models.audit import AuditLog
from app.services.auth import AuthenticationService, get_auth_service
from app.services.audit import AuditService
from app.schemas.admin import (
    UserManagementResponse, UserCreateRequest, UserUpdateRequest,
    SystemStatsResponse, AuditLogResponse
)
from app.core.exceptions import NotFoundError, ValidationError, InternalError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency to require admin role."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user


@router.get("/users", response_model=List[UserManagementResponse])
async def list_users(
    limit: int = Query(100, ge=1, le=500, description="Maximum number of users to return"),
    offset: int = Query(0, ge=0, description="Number of users to skip"),
    role: Optional[UserRole] = Query(None, description="Filter by user role"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search by username or email"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    List all users with filtering and pagination (admin only).
    
    - **limit**: Maximum number of users to return (1-500)
    - **offset**: Number of users to skip for pagination
    - **role**: Filter by user role
    - **is_active**: Filter by active status
    - **search**: Search by username or email
    """
    try:
        # Build query
        stmt = select(User).order_by(User.created_at.desc())
        
        # Apply filters
        conditions = []
        if role:
            conditions.append(User.role == role)
        if is_active is not None:
            conditions.append(User.is_active == is_active)
        if search:
            search_term = f"%{search.lower()}%"
            conditions.append(
                or_(
                    User.username.ilike(search_term),
                    User.email.ilike(search_term)
                )
            )
        
        if conditions:
            stmt = stmt.where(and_(*conditions))
        
        stmt = stmt.limit(limit).offset(offset)
        
        result = await db.execute(stmt)
        users = result.scalars().all()
        
        # Convert to response format
        user_responses = []
        for user in users:
            # Get user stats
            doc_count = await _get_user_document_count(db, user.id)
            last_activity = await _get_user_last_activity(db, user.id)
            
            user_responses.append(UserManagementResponse(
                id=str(user.id),
                username=user.username,
                email=user.email,
                role=user.role,
                is_active=user.is_active,
                theme_preference=user.theme_preference,
                created_at=user.created_at,
                last_login_at=user.last_login_at,
                document_count=doc_count,
                last_activity_at=last_activity
            ))
        
        return user_responses
        
    except Exception as e:
        logger.error(f"Error listing users: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list users"
        )


@router.post("/users", response_model=UserManagementResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreateRequest,
    current_user: User = Depends(require_admin),
    auth_service: AuthenticationService = Depends(get_auth_service),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new user (admin only).
    
    - **username**: Unique username (required)
    - **email**: Unique email address (required)
    - **password**: User password (required)
    - **role**: User role (default: user)
    - **is_active**: Whether user is active (default: true)
    """
    try:
        # Create user through auth service
        user = await auth_service.create_user(
            username=user_data.username,
            email=user_data.email,
            password=user_data.password,
            role=user_data.role,
            is_active=user_data.is_active
        )
        
        logger.info(f"Admin {current_user.username} created user {user.username}")
        
        return UserManagementResponse(
            id=str(user.id),
            username=user.username,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            theme_preference=user.theme_preference,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
            document_count=0,
            last_activity_at=None
        )
        
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user"
        )


@router.get("/users/{user_id}", response_model=UserManagementResponse)
async def get_user(
    user_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed user information (admin only).
    
    - **user_id**: UUID of the user to retrieve
    """
    try:
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found"
            )
        
        # Get user stats
        doc_count = await _get_user_document_count(db, user.id)
        last_activity = await _get_user_last_activity(db, user.id)
        
        return UserManagementResponse(
            id=str(user.id),
            username=user.username,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            theme_preference=user.theme_preference,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
            document_count=doc_count,
            last_activity_at=last_activity
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user"
        )


@router.put("/users/{user_id}", response_model=UserManagementResponse)
async def update_user(
    user_id: uuid.UUID,
    user_data: UserUpdateRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Update user information (admin only).
    
    - **user_id**: UUID of the user to update
    - **role**: New user role (optional)
    - **is_active**: New active status (optional)
    - **email**: New email address (optional)
    """
    try:
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found"
            )
        
        # Update fields
        if user_data.role is not None:
            user.role = user_data.role
        if user_data.is_active is not None:
            user.is_active = user_data.is_active
        if user_data.email is not None:
            user.email = user_data.email
        
        await db.commit()
        await db.refresh(user)
        
        logger.info(f"Admin {current_user.username} updated user {user.username}")
        
        # Get user stats
        doc_count = await _get_user_document_count(db, user.id)
        last_activity = await _get_user_last_activity(db, user.id)
        
        return UserManagementResponse(
            id=str(user.id),
            username=user.username,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            theme_preference=user.theme_preference,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
            document_count=doc_count,
            last_activity_at=last_activity
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user {user_id}: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user"
        )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a user (admin only).
    
    - **user_id**: UUID of the user to delete
    
    This will deactivate the user rather than hard delete to preserve audit trails.
    """
    try:
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found"
            )
        
        # Prevent self-deletion
        if user_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete your own account"
            )
        
        # Soft delete by deactivating
        user.is_active = False
        await db.commit()
        
        logger.info(f"Admin {current_user.username} deactivated user {user.username}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user"
        )


@router.get("/stats/system", response_model=SystemStatsResponse)
async def get_system_stats(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get system statistics and metrics (admin only).
    
    Returns comprehensive system statistics including user counts,
    document counts, activity metrics, and system health indicators.
    """
    try:
        # User statistics
        total_users = await db.scalar(select(func.count(User.id)))
        active_users = await db.scalar(
            select(func.count(User.id)).where(User.is_active == True)
        )
        admin_users = await db.scalar(
            select(func.count(User.id)).where(User.role == UserRole.ADMIN)
        )
        
        # Document statistics
        total_documents = await db.scalar(select(func.count(Document.id)))
        published_documents = await db.scalar(
            select(func.count(Document.id)).where(Document.status == "published")
        )
        draft_documents = await db.scalar(
            select(func.count(Document.id)).where(Document.status == "draft")
        )
        
        # Recent activity (last 24 hours)
        yesterday = datetime.utcnow() - timedelta(days=1)
        recent_activity = await db.scalar(
            select(func.count(AuditLog.id)).where(AuditLog.created_at >= yesterday)
        )
        
        # New users (last 7 days)
        week_ago = datetime.utcnow() - timedelta(days=7)
        new_users = await db.scalar(
            select(func.count(User.id)).where(User.created_at >= week_ago)
        )
        
        # New documents (last 7 days)
        new_documents = await db.scalar(
            select(func.count(Document.id)).where(Document.created_at >= week_ago)
        )
        
        return SystemStatsResponse(
            total_users=total_users or 0,
            active_users=active_users or 0,
            admin_users=admin_users or 0,
            total_documents=total_documents or 0,
            published_documents=published_documents or 0,
            draft_documents=draft_documents or 0,
            recent_activity_24h=recent_activity or 0,
            new_users_7d=new_users or 0,
            new_documents_7d=new_documents or 0,
            generated_at=datetime.utcnow()
        )
        
    except Exception as e:
        logger.error(f"Error getting system stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve system statistics"
        )


@router.get("/audit-logs", response_model=List[AuditLogResponse])
async def get_audit_logs(
    limit: int = Query(100, ge=1, le=500, description="Maximum number of logs to return"),
    offset: int = Query(0, ge=0, description="Number of logs to skip"),
    user_id: Optional[uuid.UUID] = Query(None, description="Filter by user ID"),
    action: Optional[str] = Query(None, description="Filter by action type"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    start_date: Optional[datetime] = Query(None, description="Filter logs after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter logs before this date"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get audit logs for compliance reporting (admin only).
    
    - **limit**: Maximum number of logs to return (1-500)
    - **offset**: Number of logs to skip for pagination
    - **user_id**: Filter by user ID
    - **action**: Filter by action type
    - **resource_type**: Filter by resource type
    - **start_date**: Filter logs after this date
    - **end_date**: Filter logs before this date
    """
    try:
        # Build query
        stmt = (
            select(AuditLog)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        
        # Apply filters
        conditions = []
        if user_id:
            conditions.append(AuditLog.user_id == user_id)
        if action:
            conditions.append(AuditLog.action == action)
        if resource_type:
            conditions.append(AuditLog.resource_type == resource_type)
        if start_date:
            conditions.append(AuditLog.created_at >= start_date)
        if end_date:
            conditions.append(AuditLog.created_at <= end_date)
        
        if conditions:
            stmt = stmt.where(and_(*conditions))
        
        result = await db.execute(stmt)
        logs = result.scalars().all()
        
        # Convert to response format
        return [
            AuditLogResponse(
                id=str(log.id),
                user_id=str(log.user_id),
                action=log.action,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                metadata=log.custom_metadata or {},
                ip_address=log.ip_address,
                user_agent=log.user_agent,
                created_at=log.created_at
            )
            for log in logs
        ]
        
    except Exception as e:
        logger.error(f"Error getting audit logs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve audit logs"
        )


async def _get_user_document_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Get count of documents created by user."""
    result = await db.execute(
        select(func.count(Document.id)).where(Document.author_id == user_id)
    )
    return result.scalar() or 0


async def _get_user_last_activity(db: AsyncSession, user_id: uuid.UUID) -> Optional[datetime]:
    """Get user's last activity timestamp."""
    result = await db.execute(
        select(AuditLog.created_at)
        .where(AuditLog.user_id == user_id)
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()