"""
Permission models for authorization and access control.
"""
import uuid
from datetime import datetime
from typing import List
from sqlalchemy import String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import enum

from app.core.database import Base


class PermissionAction(str, enum.Enum):
    """Permission action enumeration."""
    READ_PAGES = "read_pages"
    READ_ASSETS = "read_assets"
    EDIT_PAGES = "edit_pages"
    DELETE_PAGES = "delete_pages"
    MANAGE_FOLDERS = "manage_folders"
    ADMIN = "admin"


class PermissionEffect(str, enum.Enum):
    """Permission effect enumeration."""
    ALLOW = "allow"
    DENY = "deny"


class PermissionGroup(Base):
    """Permission group model for organizing permissions."""
    
    __tablename__ = "permission_groups"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Group information
    name: Mapped[str] = mapped_column(
        String(100), 
        unique=True, 
        nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now()
    )
    
    # Relationships
    permissions: Mapped[List["Permission"]] = relationship(
        "Permission", 
        back_populates="group",
        cascade="all, delete-orphan"
    )
    user_groups: Mapped[List["UserGroup"]] = relationship(
        "UserGroup", 
        back_populates="group"
    )
    
    def __repr__(self) -> str:
        return f"<PermissionGroup(id={self.id}, name='{self.name}')>"


class Permission(Base):
    """Permission model for access control rules."""
    
    __tablename__ = "permissions"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Permission details
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("permission_groups.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    resource_pattern: Mapped[str] = mapped_column(
        Text, 
        nullable=False,
        index=True
    )  # e.g., '/docs/private/*'
    action: Mapped[PermissionAction] = mapped_column(
        Enum(PermissionAction), 
        nullable=False
    )
    effect: Mapped[PermissionEffect] = mapped_column(
        Enum(PermissionEffect), 
        nullable=False
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now()
    )
    
    # Relationships
    group: Mapped["PermissionGroup"] = relationship(
        "PermissionGroup", 
        back_populates="permissions"
    )
    
    def __repr__(self) -> str:
        return f"<Permission(id={self.id}, pattern='{self.resource_pattern}', action='{self.action}', effect='{self.effect}')>"


class UserGroup(Base):
    """Association table for user-group many-to-many relationship."""
    
    __tablename__ = "user_groups"
    
    # Composite primary key
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("users.id", ondelete="CASCADE"), 
        primary_key=True
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("permission_groups.id", ondelete="CASCADE"), 
        primary_key=True
    )
    
    # Timestamp
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now()
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="user_groups")
    group: Mapped["PermissionGroup"] = relationship("PermissionGroup", back_populates="user_groups")
    
    def __repr__(self) -> str:
        return f"<UserGroup(user_id={self.user_id}, group_id={self.group_id})>"