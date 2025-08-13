"""
Comment schemas for API requests and responses.
"""
import uuid
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class CommentCreate(BaseModel):
    """Schema for creating a new comment."""
    content: str = Field(..., min_length=1, max_length=10000, description="Comment content")
    parent_id: Optional[uuid.UUID] = Field(None, description="Parent comment ID for threaded replies")


class CommentUpdate(BaseModel):
    """Schema for updating a comment."""
    content: str = Field(..., min_length=1, max_length=10000, description="Updated comment content")


class CommentResponse(BaseModel):
    """Schema for comment response."""
    id: str
    content: str
    document_id: str
    author_id: str
    author_username: str
    parent_id: Optional[str] = None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    replies: List['CommentResponse'] = []
    reply_count: int = 0


class CommentListResponse(BaseModel):
    """Schema for comment list response (without nested replies)."""
    id: str
    content: str
    document_id: str
    author_id: str
    author_username: str
    parent_id: Optional[str] = None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    reply_count: int = 0


# Enable forward references for recursive model
CommentResponse.model_rebuild()