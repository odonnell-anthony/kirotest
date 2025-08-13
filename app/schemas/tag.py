"""
Tag schemas for API requests and responses.
"""
import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, validator
import re


class TagBase(BaseModel):
    """Base tag schema with common fields."""
    name: str = Field(..., min_length=1, max_length=50, description="Tag name")
    description: Optional[str] = Field(None, max_length=500, description="Tag description")
    color: Optional[str] = Field(None, regex=r"^#[0-9A-Fa-f]{6}$", description="Hex color code")
    
    @validator('name')
    def validate_name(cls, v):
        """Validate tag name format."""
        if not v or not v.strip():
            raise ValueError('Tag name cannot be empty')
        
        # Clean and normalize the name
        name = v.strip().lower()
        
        # Check for valid characters (alphanumeric, hyphens, underscores)
        if not re.match(r'^[a-zA-Z0-9_-]+$', name):
            raise ValueError('Tag name can only contain letters, numbers, hyphens, and underscores')
        
        return name


class TagCreate(TagBase):
    """Schema for creating a new tag."""
    pass


class TagUpdate(BaseModel):
    """Schema for updating an existing tag."""
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    description: Optional[str] = Field(None, max_length=500)
    color: Optional[str] = Field(None, regex=r"^#[0-9A-Fa-f]{6}$")
    
    @validator('name')
    def validate_name(cls, v):
        """Validate tag name format if provided."""
        if v is not None:
            if not v or not v.strip():
                raise ValueError('Tag name cannot be empty')
            
            # Clean and normalize the name
            name = v.strip().lower()
            
            # Check for valid characters
            if not re.match(r'^[a-zA-Z0-9_-]+$', name):
                raise ValueError('Tag name can only contain letters, numbers, hyphens, and underscores')
            
            return name
        return v


class TagResponse(TagBase):
    """Schema for tag responses."""
    id: uuid.UUID
    usage_count: int = Field(..., description="Number of documents using this tag")
    created_at: datetime
    
    class Config:
        from_attributes = True


class TagSuggestion(BaseModel):
    """Schema for tag suggestions."""
    name: str
    usage_count: int
    similarity_score: Optional[float] = None


class TagUsageInfo(BaseModel):
    """Schema for tag usage information."""
    tag_id: uuid.UUID
    tag_name: str
    document_count: int
    recent_documents: List[str] = Field(..., description="Recent document titles using this tag")


class TagRenameRequest(BaseModel):
    """Schema for tag rename requests."""
    old_name: str = Field(..., min_length=1, max_length=50)
    new_name: str = Field(..., min_length=1, max_length=50)
    
    @validator('old_name', 'new_name')
    def validate_names(cls, v):
        """Validate tag names."""
        if not v or not v.strip():
            raise ValueError('Tag name cannot be empty')
        
        name = v.strip().lower()
        if not re.match(r'^[a-zA-Z0-9_-]+$', name):
            raise ValueError('Tag name can only contain letters, numbers, hyphens, and underscores')
        
        return name


class TagDeleteResponse(BaseModel):
    """Schema for tag deletion responses."""
    success: bool
    message: str
    affected_documents: int = Field(..., description="Number of documents that were affected")


class TagAutocompleteResponse(BaseModel):
    """Schema for tag autocomplete responses."""
    suggestions: List[TagSuggestion]
    total_count: int
    query_time_ms: float