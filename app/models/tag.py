"""
Tag model for content categorization.
"""
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Tag(Base):
    """Tag model for categorizing documents."""
    
    __tablename__ = "tags"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Tag information
    name: Mapped[str] = mapped_column(
        String(50), 
        unique=True, 
        nullable=False,
        index=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)  # Hex color code
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now()
    )
    
    # Relationships
    document_tags: Mapped[List["DocumentTag"]] = relationship(
        "DocumentTag", 
        back_populates="tag",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<Tag(id={self.id}, name='{self.name}', usage_count={self.usage_count})>"


class DocumentTag(Base):
    """Association table for document-tag many-to-many relationship."""
    
    __tablename__ = "document_tags"
    
    # Composite primary key
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("documents.id", ondelete="CASCADE"), 
        primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("tags.id", ondelete="CASCADE"), 
        primary_key=True,
        index=True
    )
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now()
    )
    
    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="tags")
    tag: Mapped["Tag"] = relationship("Tag", back_populates="document_tags")
    
    def __repr__(self) -> str:
        return f"<DocumentTag(document_id={self.document_id}, tag_id={self.tag_id})>"