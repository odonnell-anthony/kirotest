"""
Audit models for security and compliance tracking.
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import enum

from app.core.database import Base


class AuditAction(str, enum.Enum):
    """Audit action enumeration."""
    # Authentication actions
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    PASSWORD_CHANGE = "password_change"
    MFA_ENABLE = "mfa_enable"
    MFA_DISABLE = "mfa_disable"
    
    # Document actions
    DOCUMENT_CREATE = "document_create"
    DOCUMENT_UPDATE = "document_update"
    DOCUMENT_DELETE = "document_delete"
    DOCUMENT_PUBLISH = "document_publish"
    DOCUMENT_UNPUBLISH = "document_unpublish"
    DOCUMENT_MOVE = "document_move"
    DOCUMENT_VIEW = "document_view"
    
    # File actions
    FILE_UPLOAD = "file_upload"
    FILE_DOWNLOAD = "file_download"
    FILE_DELETE = "file_delete"
    FILE_MOVE = "file_move"
    
    # Permission actions
    PERMISSION_GRANT = "permission_grant"
    PERMISSION_REVOKE = "permission_revoke"
    PERMISSION_CHECK = "permission_check"
    PERMISSION_DENIED = "permission_denied"
    
    # Administrative actions
    USER_CREATE = "user_create"
    USER_UPDATE = "user_update"
    USER_DELETE = "user_delete"
    USER_ACTIVATE = "user_activate"
    USER_DEACTIVATE = "user_deactivate"
    
    # System actions
    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"
    BACKUP_CREATE = "backup_create"
    BACKUP_RESTORE = "backup_restore"


class AuditSeverity(str, enum.Enum):
    """Audit severity enumeration."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AuditLog(Base):
    """Audit log model for security and compliance tracking."""
    
    __tablename__ = "audit_logs"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Audit information
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction), 
        nullable=False,
        index=True
    )
    severity: Mapped[AuditSeverity] = mapped_column(
        Enum(AuditSeverity), 
        default=AuditSeverity.LOW,
        index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    
    # User and session information
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("users.id"), 
        nullable=True,
        index=True
    )
    session_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Network information
    ip_address: Mapped[Optional[str]] = mapped_column(INET, nullable=True, index=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Resource information
    resource_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    resource_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Request information
    request_method: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    request_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    request_params: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # Response information
    response_status: Mapped[Optional[int]] = mapped_column(nullable=True)
    response_time_ms: Mapped[Optional[int]] = mapped_column(nullable=True)
    
    # Additional metadata
    custom_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        index=True
    )
    
    # Relationships
    user: Mapped[Optional["User"]] = relationship("User")
    
    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action='{self.action}', user_id={self.user_id})>"


class DataRetentionPolicy(Base):
    """Data retention policy model for compliance."""
    
    __tablename__ = "data_retention_policies"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Policy information
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Retention settings
    table_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    retention_days: Mapped[int] = mapped_column(nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        onupdate=func.now()
    )
    
    def __repr__(self) -> str:
        return f"<DataRetentionPolicy(name='{self.name}', table='{self.table_name}', days={self.retention_days})>"


class SecurityEvent(Base):
    """Security event model for threat detection and monitoring."""
    
    __tablename__ = "security_events"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Event information
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    severity: Mapped[AuditSeverity] = mapped_column(
        Enum(AuditSeverity), 
        nullable=False,
        index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Source information
    source_ip: Mapped[Optional[str]] = mapped_column(INET, nullable=True, index=True)
    source_user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("users.id"), 
        nullable=True,
        index=True
    )
    
    # Detection information
    detection_method: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence_score: Mapped[Optional[float]] = mapped_column(nullable=True)
    
    # Response information
    is_resolved: Mapped[bool] = mapped_column(default=False, index=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        nullable=True
    )
    resolved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("users.id"), 
        nullable=True
    )
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Additional data
    event_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    
    # Timestamps
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        index=True
    )
    
    # Relationships
    source_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[source_user_id])
    resolved_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[resolved_by_id])
    
    def __repr__(self) -> str:
        return f"<SecurityEvent(id={self.id}, type='{self.event_type}', severity='{self.severity}')>"