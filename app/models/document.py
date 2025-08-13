"""
Document model for content management.
"""
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Text, DateTime, Enum, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import enum

from app.core.database import Base


class ContentFormat(str, enum.Enum):
    """Content format enumeration."""
    MARKDOWN = "markdown"
    HTML = "html"


class DocumentStatus(str, enum.Enum):
    """Document status enumeration."""
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Document(Base):
    """Document model for wiki pages and content."""
    
    __tablename__ = "documents"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Document content
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[ContentFormat] = mapped_column(
        Enum(ContentFormat), 
        default=ContentFormat.MARKDOWN
    )
    
    # Organization
    folder_path: Mapped[str] = mapped_column(
        Text, 
        nullable=False, 
        default="/",
        index=True
    )
    
    # Status and visibility
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus), 
        default=DocumentStatus.DRAFT,
        index=True
    )
    
    # Author relationship
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("users.id"), 
        nullable=False,
        index=True
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        onupdate=func.now(),
        index=True
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        nullable=True
    )
    
    # Full-text search vector (automatically updated by trigger)
    search_vector: Mapped[Optional[str]] = mapped_column(TSVECTOR, nullable=True)
    
    # Additional metadata
    custom_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    
    # Relationships
    author: Mapped["User"] = relationship("User", back_populates="documents")
    revisions: Mapped[List["DocumentRevision"]] = relationship(
        "DocumentRevision", 
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentRevision.revision_number.desc()"
    )
    tags: Mapped[List["DocumentTag"]] = relationship(
        "DocumentTag", 
        back_populates="document",
        cascade="all, delete-orphan"
    )
    comments: Mapped[List["Comment"]] = relationship(
        "Comment", 
        back_populates="document",
        cascade="all, delete-orphan"
    )
    files: Mapped[List["File"]] = relationship(
        "File", 
        back_populates="document"
    )
    

    # Constraints
    __table_args__ = (
        UniqueConstraint('folder_path', 'slug', name='uq_document_path_slug'),
        CheckConstraint(
            "folder_path ~ '^(/[a-zA-Z0-9_-]+)*/$'",
            name='ck_document_valid_folder_path'
        ),
    )
    
    def __repr__(self) -> str:
        return f"<Document(id={self.id}, title='{self.title}', status='{self.status}')>"