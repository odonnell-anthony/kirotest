"""
Document schemas for API request/response models.
"""
import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, validator
import re
import bleach

from app.models.document import DocumentStatus, ContentFormat


class DocumentBase(BaseModel):
    """Base document schema with common fields."""
    title: str = Field(..., min_length=1, max_length=255, description="Document title")
    content: str = Field(..., description="Document content in markdown or HTML")
    folder_path: str = Field(default="/", description="Folder path for organization")
    content_type: ContentFormat = Field(default=ContentFormat.MARKDOWN, description="Content format")
    status: DocumentStatus = Field(default=DocumentStatus.DRAFT, description="Document status")
    
    @validator('title')
    def validate_title(cls, v):
        """Validate and sanitize title."""
        if not v or len(v.strip()) == 0:
            raise ValueError('Title cannot be empty')
        # Sanitize HTML but allow basic formatting
        sanitized = bleach.clean(v.strip(), tags=[], strip=True)
        return sanitized
    
    @validator('content')
    def validate_content(cls, v):
        """Validate and sanitize content."""
        if not v:
            return ""
        # For markdown, we allow more tags but still sanitize
        allowed_tags = [
            'p', 'br', 'strong', 'em', 'code', 'pre', 'blockquote',
            'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'ul', 'ol', 'li', 'a', 'img', 'table', 'thead', 'tbody', 'tr', 'td', 'th'
        ]
        allowed_attributes = {
            'a': ['href', 'title'],
            'img': ['src', 'alt', 'title', 'width', 'height'],
            'code': ['class'],
            'pre': ['class']
        }
        return bleach.clean(v, tags=allowed_tags, attributes=allowed_attributes, strip=True)
    
    @validator('folder_path')
    def validate_folder_path(cls, v):
        """Validate folder path format."""
        if not v:
            return "/"
        # Ensure path starts with / and follows valid format
        if not v.startswith('/'):
            v = '/' + v
        # Ensure path ends with / for consistency
        if not v.endswith('/'):
            v = v + '/'
        # Validate path format
        if not re.match(r'^(/[a-zA-Z0-9_-]+)*/$', v):
            raise ValueError('Invalid folder path format. Use alphanumeric characters, hyphens, and underscores only.')
        return v


class DocumentCreate(DocumentBase):
    """Schema for creating a new document."""
    tags: List[str] = Field(default=[], description="List of tag names")
    
    @validator('tags')
    def validate_tags(cls, v):
        """Validate tag names."""
        if not v:
            return []
        validated_tags = []
        for tag in v:
            if isinstance(tag, str) and tag.strip():
                # Sanitize tag name
                clean_tag = bleach.clean(tag.strip(), tags=[], strip=True)
                if len(clean_tag) <= 50:  # Max tag length
                    validated_tags.append(clean_tag)
        return validated_tags


class DocumentUpdate(BaseModel):
    """Schema for updating an existing document."""
    title: Optional[str] = Field(None, min_length=1, max_length=255, description="Document title")
    content: Optional[str] = Field(None, description="Document content")
    folder_path: Optional[str] = Field(None, description="Folder path for organization")
    content_type: Optional[ContentFormat] = Field(None, description="Content format")
    status: Optional[DocumentStatus] = Field(None, description="Document status")
    tags: Optional[List[str]] = Field(None, description="List of tag names")
    change_summary: Optional[str] = Field(None, max_length=500, description="Summary of changes made")
    
    @validator('title')
    def validate_title(cls, v):
        """Validate and sanitize title."""
        if v is not None:
            if not v or len(v.strip()) == 0:
                raise ValueError('Title cannot be empty')
            return bleach.clean(v.strip(), tags=[], strip=True)
        return v
    
    @validator('content')
    def validate_content(cls, v):
        """Validate and sanitize content."""
        if v is not None:
            allowed_tags = [
                'p', 'br', 'strong', 'em', 'code', 'pre', 'blockquote',
                'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                'ul', 'ol', 'li', 'a', 'img', 'table', 'thead', 'tbody', 'tr', 'td', 'th'
            ]
            allowed_attributes = {
                'a': ['href', 'title'],
                'img': ['src', 'alt', 'title', 'width', 'height'],
                'code': ['class'],
                'pre': ['class']
            }
            return bleach.clean(v, tags=allowed_tags, attributes=allowed_attributes, strip=True)
        return v
    
    @validator('folder_path')
    def validate_folder_path(cls, v):
        """Validate folder path format."""
        if v is not None:
            if not v.startswith('/'):
                v = '/' + v
            if not v.endswith('/'):
                v = v + '/'
            if not re.match(r'^(/[a-zA-Z0-9_-]+)*/$', v):
                raise ValueError('Invalid folder path format. Use alphanumeric characters, hyphens, and underscores only.')
        return v
    
    @validator('tags')
    def validate_tags(cls, v):
        """Validate tag names."""
        if v is not None:
            if not v:
                return []
            validated_tags = []
            for tag in v:
                if isinstance(tag, str) and tag.strip():
                    clean_tag = bleach.clean(tag.strip(), tags=[], strip=True)
                    if len(clean_tag) <= 50:
                        validated_tags.append(clean_tag)
            return validated_tags
        return v
    
    @validator('change_summary')
    def validate_change_summary(cls, v):
        """Validate and sanitize change summary."""
        if v is not None:
            return bleach.clean(v.strip(), tags=[], strip=True)
        return v


class DocumentMoveRequest(BaseModel):
    """Schema for moving a document to a different folder."""
    new_folder_path: str = Field(..., description="New folder path")
    
    @validator('new_folder_path')
    def validate_folder_path(cls, v):
        """Validate folder path format."""
        if not v.startswith('/'):
            v = '/' + v
        if not v.endswith('/'):
            v = v + '/'
        if not re.match(r'^(/[a-zA-Z0-9_-]+)*/$', v):
            raise ValueError('Invalid folder path format. Use alphanumeric characters, hyphens, and underscores only.')
        return v


class DocumentRevisionResponse(BaseModel):
    """Schema for document revision response."""
    id: str
    document_id: str
    revision_number: int
    title: str
    content: str
    change_summary: Optional[str] = None
    author_id: str
    author_username: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class DocumentRevisionListResponse(BaseModel):
    """Schema for document revision list response."""
    id: str
    document_id: str
    revision_number: int
    title: str
    change_summary: Optional[str] = None
    author_id: str
    author_username: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class DocumentRevisionRestoreRequest(BaseModel):
    """Schema for restoring a document revision."""
    change_summary: Optional[str] = Field(None, max_length=500, description="Summary for the restoration")
    
    @validator('change_summary')
    def validate_change_summary(cls, v):
        """Validate and sanitize change summary."""
        if v is not None:
            return bleach.clean(v.strip(), tags=[], strip=True)
        return v


class DocumentRevisionComparisonResponse(BaseModel):
    """Schema for document revision comparison response."""
    document_id: str
    revision1: dict
    revision2: dict
    changes: dict
    
    class Config:
        from_attributes = True