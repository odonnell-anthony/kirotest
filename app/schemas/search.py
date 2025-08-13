"""
Pydantic schemas for search functionality.
"""
import uuid
from typing import List, Optional
from pydantic import BaseModel, Field, validator
from datetime import datetime

from app.models.document import DocumentStatus


class SearchFiltersSchema(BaseModel):
    """Schema for search filters."""
    folder_path: Optional[str] = Field(None, description="Filter by folder path")
    tags: Optional[List[str]] = Field(None, description="Filter by tags (AND logic)")
    status: Optional[DocumentStatus] = Field(None, description="Filter by document status")
    author_id: Optional[uuid.UUID] = Field(None, description="Filter by author ID")
    date_from: Optional[str] = Field(None, description="Filter by date from (ISO format)")
    date_to: Optional[str] = Field(None, description="Filter by date to (ISO format)")
    
    @validator('tags')
    def validate_tags(cls, v):
        if v is not None:
            # Remove empty strings and duplicates
            return list(set([tag.strip() for tag in v if tag.strip()]))
        return v


class SearchResultSchema(BaseModel):
    """Schema for individual search result."""
    document_id: uuid.UUID = Field(..., description="Document ID")
    title: str = Field(..., description="Document title")
    slug: str = Field(..., description="Document slug")
    folder_path: str = Field(..., description="Document folder path")
    content_snippet: str = Field(..., description="Content snippet with context")
    highlighted_title: str = Field(..., description="Title with search term highlighting")
    highlighted_snippet: str = Field(..., description="Content snippet with search term highlighting")
    rank: float = Field(..., description="Search relevance rank")
    tags: List[str] = Field(..., description="Document tags")
    author_name: str = Field(..., description="Author username")
    updated_at: str = Field(..., description="Last updated timestamp (ISO format)")
    status: str = Field(..., description="Document status")
    
    class Config:
        from_attributes = True


class SearchResultsSchema(BaseModel):
    """Schema for search results container."""
    results: List[SearchResultSchema] = Field(..., description="List of search results")
    total_count: int = Field(..., description="Total number of matching documents")
    query: str = Field(..., description="Original search query")
    filters: SearchFiltersSchema = Field(..., description="Applied search filters")
    execution_time_ms: float = Field(..., description="Search execution time in milliseconds")
    
    class Config:
        from_attributes = True


class AutocompleteRequest(BaseModel):
    """Schema for autocomplete request."""
    partial: str = Field(..., min_length=1, max_length=50, description="Partial text for autocomplete")
    limit: int = Field(10, ge=1, le=20, description="Maximum number of suggestions")


class AutocompleteResponse(BaseModel):
    """Schema for autocomplete response."""
    suggestions: List[str] = Field(..., description="List of autocomplete suggestions")
    execution_time_ms: float = Field(..., description="Autocomplete execution time in milliseconds")


class SearchSuggestionsRequest(BaseModel):
    """Schema for search suggestions request."""
    query: str = Field(..., min_length=2, max_length=100, description="Partial search query")
    limit: int = Field(5, ge=1, le=10, description="Maximum number of suggestions")


class SearchSuggestionsResponse(BaseModel):
    """Schema for search suggestions response."""
    suggestions: List[str] = Field(..., description="List of search suggestions")
    execution_time_ms: float = Field(..., description="Suggestions execution time in milliseconds")


class SearchAnalytics(BaseModel):
    """Schema for search analytics data."""
    query: str = Field(..., description="Search query")
    user_id: uuid.UUID = Field(..., description="User who performed the search")
    results_count: int = Field(..., description="Number of results returned")
    execution_time_ms: float = Field(..., description="Search execution time")
    filters_applied: SearchFiltersSchema = Field(..., description="Filters that were applied")
    timestamp: datetime = Field(..., description="When the search was performed")
    
    class Config:
        from_attributes = True