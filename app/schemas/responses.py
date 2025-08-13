"""
Response schemas for API endpoints.
"""
import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel

from app.models.document import DocumentStatus, ContentFormat


class TagResponse(BaseModel):
    """Schema for tag response."""
    id: str
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    usage_count: int
    
    class Config:
        from_attributes = True


class DocumentResponse(BaseModel):
    """Schema for document response."""
    id: str
    title: str
    slug: str
    content: str
    content_type: ContentFormat
    folder_path: str
    status: DocumentStatus
    author_id: str
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None
    tags: List[TagResponse] = []
    
    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    """Schema for document list response."""
    id: str
    title: str
    slug: str
    folder_path: str
    status: DocumentStatus
    author_id: str
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None
    tags: List[TagResponse] = []
    
    class Config:
        from_attributes = True


class FolderResponse(BaseModel):
    """Schema for folder response."""
    id: str
    name: str
    path: str
    parent_path: Optional[str] = None
    description: Optional[str] = None
    created_by_id: str
    created_at: datetime
    
    class Config:
        from_attributes = True