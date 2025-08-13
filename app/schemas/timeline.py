"""
Timeline schemas for API requests and responses.
"""
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class TimelineEventType(str, Enum):
    """Timeline event types."""
    DOCUMENT_CREATED = "document_created"
    DOCUMENT_UPDATED = "document_updated"
    DOCUMENT_PUBLISHED = "document_published"
    DOCUMENT_MOVED = "document_moved"
    DOCUMENT_DELETED = "document_deleted"
    COMMENT_CREATED = "comment_created"
    COMMENT_UPDATED = "comment_updated"
    COMMENT_DELETED = "comment_deleted"
    FOLDER_CREATED = "folder_created"
    FOLDER_UPDATED = "folder_updated"
    FOLDER_MOVED = "folder_moved"
    FOLDER_DELETED = "folder_deleted"
    TAG_ADDED = "tag_added"
    TAG_REMOVED = "tag_removed"


class TimelineEventResponse(BaseModel):
    """Schema for timeline event response."""
    id: str
    event_type: TimelineEventType
    title: str
    description: str
    user_id: str
    user_username: str
    document_id: Optional[str] = None
    document_title: Optional[str] = None
    folder_path: Optional[str] = None
    metadata: Dict[str, Any] = {}
    created_at: datetime


class TimelineResponse(BaseModel):
    """Schema for timeline response with pagination."""
    events: List[TimelineEventResponse]
    total_count: int
    has_more: bool
    next_offset: Optional[int] = None


class DocumentTimelineResponse(BaseModel):
    """Schema for document-specific timeline response."""
    document_id: str
    document_title: str
    events: List[TimelineEventResponse]
    total_count: int


class UserActivityResponse(BaseModel):
    """Schema for user activity timeline response."""
    user_id: str
    user_username: str
    events: List[TimelineEventResponse]
    total_count: int
    activity_summary: Dict[str, int] = {}  # Event type counts