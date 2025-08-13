"""
Folder schemas for API requests and responses.
"""
import re
from typing import Optional, List
from pydantic import BaseModel, Field, validator


class FolderCreate(BaseModel):
    """Schema for creating a new folder."""
    name: str = Field(..., min_length=1, max_length=100, description="Folder name")
    path: str = Field(..., description="Full folder path")
    parent_path: Optional[str] = Field(None, description="Parent folder path")
    description: Optional[str] = Field(None, max_length=500, description="Folder description")
    
    @validator('name')
    def validate_name(cls, v):
        """Validate folder name format."""
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('Folder name must contain only alphanumeric characters, hyphens, and underscores')
        return v
    
    @validator('path')
    def validate_path(cls, v):
        """Validate folder path format."""
        if not v.startswith('/'):
            v = '/' + v
        if not v.endswith('/'):
            v = v + '/'
        if not re.match(r'^(/[a-zA-Z0-9_-]+)+/$', v):
            raise ValueError('Invalid folder path format. Use alphanumeric characters, hyphens, and underscores only.')
        return v
    
    @validator('parent_path')
    def validate_parent_path(cls, v):
        """Validate parent folder path format."""
        if v is not None:
            if not v.startswith('/'):
                v = '/' + v
            if not v.endswith('/'):
                v = v + '/'
            if not re.match(r'^(/[a-zA-Z0-9_-]+)*/$', v):
                raise ValueError('Invalid parent path format. Use alphanumeric characters, hyphens, and underscores only.')
        return v


class FolderUpdate(BaseModel):
    """Schema for updating a folder."""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="Folder name")
    description: Optional[str] = Field(None, max_length=500, description="Folder description")
    
    @validator('name')
    def validate_name(cls, v):
        """Validate folder name format."""
        if v is not None and not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('Folder name must contain only alphanumeric characters, hyphens, and underscores')
        return v


class FolderMoveRequest(BaseModel):
    """Schema for moving a folder to a different parent."""
    new_parent_path: Optional[str] = Field(None, description="New parent folder path (null for root)")
    
    @validator('new_parent_path')
    def validate_parent_path(cls, v):
        """Validate parent folder path format."""
        if v is not None:
            if not v.startswith('/'):
                v = '/' + v
            if not v.endswith('/'):
                v = v + '/'
            if not re.match(r'^(/[a-zA-Z0-9_-]+)*/$', v):
                raise ValueError('Invalid parent path format. Use alphanumeric characters, hyphens, and underscores only.')
        return v


class FolderTreeNode(BaseModel):
    """Schema for folder tree node."""
    id: str
    name: str
    path: str
    parent_path: Optional[str] = None
    description: Optional[str] = None
    created_by_id: str
    created_at: str
    children: List['FolderTreeNode'] = []
    document_count: int = 0


class FolderListResponse(BaseModel):
    """Schema for folder list response."""
    id: str
    name: str
    path: str
    parent_path: Optional[str] = None
    description: Optional[str] = None
    created_by_id: str
    created_at: str
    document_count: int = 0


# Enable forward references for recursive model
FolderTreeNode.model_rebuild()