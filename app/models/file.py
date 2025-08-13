"""
File model for asset management.
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, DateTime, ForeignKey, BigInteger, CheckConstraint, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class File(Base):
    """File model for managing uploaded assets."""
    
    __tablename__ = "files"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # File information
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(
        Text, 
        unique=True, 
        nullable=False,
        index=True
    )
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum: Mapped[str] = mapped_column(
        String(64), 
        nullable=False,
        index=True
    )  # SHA-256 hash for integrity verification
    
    # Relationships
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("users.id"), 
        nullable=False
    )
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("documents.id"), 
        nullable=True,
        index=True
    )  # Optional association with document
    
    # Security and audit fields
    is_malware_scanned: Mapped[bool] = mapped_column(Boolean, default=False)
    malware_scan_result: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        nullable=True
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now()
    )
    
    # Relationships
    uploaded_by_user: Mapped["User"] = relationship("User", back_populates="uploaded_files", foreign_keys=[uploaded_by])
    document: Mapped[Optional["Document"]] = relationship("Document", back_populates="files")
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            "file_size > 0 AND file_size <= 104857600", 
            name='ck_file_valid_size'
        ),  # 100MB limit
    )
    
    def __repr__(self) -> str:
        return f"<File(id={self.id}, filename='{self.filename}', size={self.file_size})>"