"""
Admin schemas for API requests and responses.
"""
import uuid
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr

from app.models.user import UserRole, ThemePreference


class UserCreateRequest(BaseModel):
    """Schema for creating a new user (admin only)."""
    username: str = Field(..., min_length=3, max_length=50, description="Unique username")
    email: EmailStr = Field(..., description="Unique email address")
    password: str = Field(..., min_length=8, description="User password")
    role: UserRole = Field(UserRole.USER, description="User role")
    is_active: bool = Field(True, description="Whether user is active")


class UserUpdateRequest(BaseModel):
    """Schema for updating user information (admin only)."""
    role: Optional[UserRole] = Field(None, description="New user role")
    is_active: Optional[bool] = Field(None, description="New active status")
    email: Optional[EmailStr] = Field(None, description="New email address")


class UserManagementResponse(BaseModel):
    """Schema for user management response."""
    id: str
    username: str
    email: str
    role: UserRole
    is_active: bool
    theme_preference: ThemePreference
    created_at: datetime
    last_login_at: Optional[datetime] = None
    document_count: int = 0
    last_activity_at: Optional[datetime] = None


class SystemStatsResponse(BaseModel):
    """Schema for system statistics response."""
    total_users: int
    active_users: int
    admin_users: int
    total_documents: int
    published_documents: int
    draft_documents: int
    recent_activity_24h: int
    new_users_7d: int
    new_documents_7d: int
    generated_at: datetime


class AuditLogResponse(BaseModel):
    """Schema for audit log response."""
    id: str
    user_id: str
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    metadata: Dict[str, Any] = {}
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime


class WebhookConfigRequest(BaseModel):
    """Schema for webhook configuration request."""
    name: str = Field(..., min_length=1, max_length=100, description="Webhook name")
    url: str = Field(..., description="Webhook URL")
    secret: Optional[str] = Field(None, description="Webhook secret for verification")
    events: list[str] = Field(..., description="List of events to trigger webhook")
    is_active: bool = Field(True, description="Whether webhook is active")


class WebhookConfigResponse(BaseModel):
    """Schema for webhook configuration response."""
    id: str
    name: str
    url: str
    events: list[str]
    is_active: bool
    created_at: datetime
    last_triggered_at: Optional[datetime] = None
    success_count: int = 0
    failure_count: int = 0


class IntegrationConfigRequest(BaseModel):
    """Schema for integration configuration request."""
    name: str = Field(..., min_length=1, max_length=100, description="Integration name")
    type: str = Field(..., description="Integration type (github, azure_devops)")
    config: Dict[str, Any] = Field(..., description="Integration-specific configuration")
    is_active: bool = Field(True, description="Whether integration is active")


class IntegrationConfigResponse(BaseModel):
    """Schema for integration configuration response."""
    id: str
    name: str
    type: str
    config: Dict[str, Any]
    is_active: bool
    created_at: datetime
    last_sync_at: Optional[datetime] = None
    sync_status: str = "pending"