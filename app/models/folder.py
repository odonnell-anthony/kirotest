"""
Folder model for hierarchical organization.
"""
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Text, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Folder(Base):
    """Folder model for organizing documents hierarchically."""
    
    __tablename__ = "folders"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Folder information
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    path: Mapped[str] = mapped_column(
        Text, 
        unique=True, 
        nullable=False,
        index=True
    )
    parent_path: Mapped[Optional[str]] = mapped_column(
        Text, 
        nullable=True,
        index=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Creator relationship
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("users.id"), 
        nullable=False
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now()
    )
    
    # Relationships
    created_by: Mapped["User"] = relationship("User", back_populates="folders_created")
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            "path ~ '^(/[a-zA-Z0-9_-]+)+/$'", 
            name='ck_folder_valid_path'
        ),
        CheckConstraint(
            "parent_path IS NULL OR parent_path ~ '^(/[a-zA-Z0-9_-]+)*/$'", 
            name='ck_folder_valid_parent'
        ),
    )
    
    def __repr__(self) -> str:
        return f"<Folder(id={self.id}, name='{self.name}', path='{self.path}')>"