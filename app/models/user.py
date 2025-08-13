"""
User model for authentication and authorization.
"""
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Boolean, DateTime, Enum, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import enum

from app.core.database import Base


class UserRole(str, enum.Enum):
    """User role enumeration."""
    ADMIN = "admin"
    NORMAL = "normal"


class ThemeType(str, enum.Enum):
    """Theme preference enumeration."""
    LIGHT = "light"
    DARK = "dark"


class User(Base):
    """User model for authentication and user management."""
    
    __tablename__ = "users"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Basic user information
    username: Mapped[str] = mapped_column(
        String(50), 
        unique=True, 
        nullable=False,
        index=True
    )
    email: Mapped[str] = mapped_column(
        String(255), 
        unique=True, 
        nullable=False,
        index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Role and status
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), 
        nullable=False, 
        default=UserRole.NORMAL
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Multi-factor authentication
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_secret: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    
    # User preferences
    theme_preference: Mapped[ThemeType] = mapped_column(
        Enum(ThemeType), 
        default=ThemeType.LIGHT
    )
    
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
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        nullable=True
    )
    
    # Relationships
    documents: Mapped[List["Document"]] = relationship(
        "Document", 
        back_populates="author",
        cascade="all, delete-orphan"
    )
    document_revisions: Mapped[List["DocumentRevision"]] = relationship(
        "DocumentRevision", 
        back_populates="author"
    )
    comments: Mapped[List["Comment"]] = relationship(
        "Comment", 
        back_populates="author"
    )
    uploaded_files: Mapped[List["File"]] = relationship(
        "File", 
        back_populates="uploaded_by"
    )
    folders_created: Mapped[List["Folder"]] = relationship(
        "Folder", 
        back_populates="created_by"
    )
    user_groups: Mapped[List["UserGroup"]] = relationship(
        "UserGroup", 
        back_populates="user"
    )
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"