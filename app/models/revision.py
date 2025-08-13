"""
Document revision model for version tracking.
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class DocumentRevision(Base):
    """Document revision model for tracking changes."""
    
    __tablename__ = "document_revisions"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Revision information
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("documents.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Content snapshot
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    change_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Author relationship
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("users.id"), 
        nullable=False
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now()
    )
    
    # Additional metadata
    custom_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    
    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="revisions")
    author: Mapped["User"] = relationship("User", back_populates="document_revisions")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('document_id', 'revision_number', name='uq_document_revision'),
    )
    
    def __repr__(self) -> str:
        return f"<DocumentRevision(id={self.id}, document_id={self.document_id}, revision={self.revision_number})>"