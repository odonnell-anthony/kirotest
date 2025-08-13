"""
Tag management API endpoints.
"""
import uuid
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from app.schemas.tag import (
    TagCreate, TagUpdate, TagResponse, TagSuggestion,
    TagUsageInfo, TagRenameRequest, TagDeleteResponse,
    TagAutocompleteResponse
)
from app.services.tag import TagService, get_tag_service
from app.services.auth import get_current_user
from app.models.user import User
from app.core.exceptions import ValidationError, NotFoundError, ConflictError
from app.core.rate_limit import limiter
from fastapi import Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tags", tags=["tags"])


@router.post("/", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")  # Allow 20 tag creations per minute
async def create_tag(
    request: Request,
    tag_data: TagCreate,
    current_user: User = Depends(get_current_user),
    tag_service: TagService = Depends(get_tag_service)
):
    """
    Create a new tag.
    
    - **name**: Tag name (required, unique, alphanumeric with hyphens/underscores)
    - **description**: Optional tag description
    - **color**: Optional hex color code (e.g., #FF5733)
    """
    try:
        return await tag_service.create_tag(tag_data, current_user)
    except ConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/", response_model=List[TagResponse])
async def list_tags(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of tags to return"),
    offset: int = Query(0, ge=0, description="Number of tags to skip"),
    sort_by: str = Query("usage_count", regex="^(name|usage_count|created_at)$", description="Field to sort by"),
    sort_order: str = Query("desc", regex="^(asc|desc)$", description="Sort order"),
    search: Optional[str] = Query(None, max_length=100, description="Search term for tag names/descriptions"),
    current_user: User = Depends(get_current_user),
    tag_service: TagService = Depends(get_tag_service)
):
    """
    List all tags with optional filtering and sorting.
    
    - **limit**: Maximum number of tags to return (1-1000)
    - **offset**: Number of tags to skip for pagination
    - **sort_by**: Field to sort by (name, usage_count, created_at)
    - **sort_order**: Sort order (asc, desc)
    - **search**: Optional search term for filtering tags
    """
    return await tag_service.list_tags(
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
        search=search
    )


@router.get("/autocomplete", response_model=TagAutocompleteResponse)
@limiter.limit("100/minute")  # High limit for autocomplete
async def autocomplete_tags(
    request: Request,
    q: str = Query(..., min_length=1, max_length=50, description="Partial tag name"),
    limit: int = Query(10, ge=1, le=50, description="Maximum number of suggestions"),
    current_user: User = Depends(get_current_user),
    tag_service: TagService = Depends(get_tag_service)
):
    """
    Get tag autocomplete suggestions with sub-100ms response time.
    
    - **q**: Partial tag name to search for
    - **limit**: Maximum number of suggestions (1-50)
    
    Returns suggestions sorted by similarity and usage count.
    """
    return await tag_service.autocomplete_tags(q, limit)


@router.get("/suggest", response_model=List[TagSuggestion])
async def suggest_tags(
    content: str = Query(..., min_length=10, description="Document content to analyze"),
    existing_tags: Optional[str] = Query(None, description="Comma-separated list of existing tags"),
    limit: int = Query(10, ge=1, le=20, description="Maximum number of suggestions"),
    current_user: User = Depends(get_current_user),
    tag_service: TagService = Depends(get_tag_service)
):
    """
    Get tag suggestions based on document content.
    
    - **content**: Document content to analyze for tag suggestions
    - **existing_tags**: Comma-separated list of tags already assigned
    - **limit**: Maximum number of suggestions (1-20)
    """
    existing_tag_list = []
    if existing_tags:
        existing_tag_list = [tag.strip() for tag in existing_tags.split(",") if tag.strip()]
    
    return await tag_service.suggest_tags(content, existing_tag_list, limit)


@router.get("/{tag_id}", response_model=TagResponse)
async def get_tag(
    tag_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    tag_service: TagService = Depends(get_tag_service)
):
    """
    Get a specific tag by ID.
    
    - **tag_id**: UUID of the tag to retrieve
    """
    try:
        return await tag_service.get_tag(tag_id)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("/{tag_id}/usage", response_model=TagUsageInfo)
async def get_tag_usage(
    tag_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    tag_service: TagService = Depends(get_tag_service)
):
    """
    Get detailed usage information for a tag.
    
    - **tag_id**: UUID of the tag to get usage info for
    
    Returns document count and list of recent documents using this tag.
    """
    try:
        return await tag_service.get_tag_usage_info(tag_id)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.put("/{tag_id}", response_model=TagResponse)
@limiter.limit("30/minute")  # Allow 30 tag updates per minute
async def update_tag(
    request: Request,
    tag_id: uuid.UUID,
    tag_data: TagUpdate,
    current_user: User = Depends(get_current_user),
    tag_service: TagService = Depends(get_tag_service)
):
    """
    Update an existing tag.
    
    - **tag_id**: UUID of the tag to update
    - **name**: New tag name (optional)
    - **description**: New tag description (optional)
    - **color**: New hex color code (optional)
    """
    try:
        return await tag_service.update_tag(tag_id, tag_data, current_user)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except ConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/rename", response_model=TagResponse)
@limiter.limit("10/minute")  # Lower limit for rename operations
async def rename_tag(
    request: Request,
    rename_request: TagRenameRequest,
    current_user: User = Depends(get_current_user),
    tag_service: TagService = Depends(get_tag_service)
):
    """
    Rename a tag with cascading updates to all associated documents.
    
    - **old_name**: Current tag name
    - **new_name**: New tag name
    
    This operation updates all documents that use the old tag name.
    """
    try:
        return await tag_service.rename_tag(rename_request, current_user)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except ConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{tag_id}", response_model=TagDeleteResponse)
@limiter.limit("10/minute")  # Lower limit for delete operations
async def delete_tag(
    request: Request,
    tag_id: uuid.UUID,
    force: bool = Query(False, description="Force deletion even if tag is in use"),
    current_user: User = Depends(get_current_user),
    tag_service: TagService = Depends(get_tag_service)
):
    """
    Delete a tag with usage validation.
    
    - **tag_id**: UUID of the tag to delete
    - **force**: Whether to force deletion even if tag is in use
    
    By default, tags that are in use cannot be deleted unless force=true.
    """
    try:
        return await tag_service.delete_tag(tag_id, current_user, force)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/update-usage-counts")
async def update_tag_usage_counts(
    current_user: User = Depends(get_current_user),
    tag_service: TagService = Depends(get_tag_service)
):
    """
    Update usage counts for all tags (admin operation).
    
    This endpoint recalculates usage counts for all tags based on current
    document associations. Useful for maintenance and data consistency.
    
    Requires admin privileges.
    """
    # Check if user is admin
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    
    try:
        updated_counts = await tag_service.update_tag_usage_counts()
        return JSONResponse(
            content={
                "message": f"Updated usage counts for {len(updated_counts)} tags",
                "updated_counts": updated_counts
            }
        )
    except Exception as e:
        logger.error(f"Error updating tag usage counts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update tag usage counts"
        )


@router.get("/name/{tag_name}", response_model=TagResponse)
async def get_tag_by_name(
    tag_name: str,
    current_user: User = Depends(get_current_user),
    tag_service: TagService = Depends(get_tag_service)
):
    """
    Get a tag by name.
    
    - **tag_name**: Name of the tag to retrieve
    """
    tag = await tag_service.get_tag_by_name(tag_name)
    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tag '{tag_name}' not found"
        )
    return tag