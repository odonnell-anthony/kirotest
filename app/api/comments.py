"""
Comment API endpoints for document discussions.
"""
import uuid
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.services.comment import CommentService
from app.schemas.comment import (
    CommentCreate, CommentUpdate, CommentResponse, CommentListResponse
)
from app.core.exceptions import (
    NotFoundError, PermissionDeniedError, ValidationError, InternalError
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["comments"])


@router.post("/documents/{document_id}/comments", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def create_comment(
    document_id: uuid.UUID,
    comment_data: CommentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new comment on a document.
    
    - **document_id**: UUID of the document to comment on
    - **content**: Comment content (required)
    - **parent_id**: Parent comment ID for threaded replies (optional)
    """
    try:
        service = CommentService(db)
        comment = await service.create_comment(document_id, comment_data, current_user)
        return _to_comment_response(comment)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)


@router.get("/documents/{document_id}/comments", response_model=List[CommentResponse])
async def get_document_comments(
    document_id: uuid.UUID,
    include_replies: bool = Query(True, description="Include nested replies"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of comments to return"),
    offset: int = Query(0, ge=0, description="Number of comments to skip"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get comments for a document.
    
    - **document_id**: UUID of the document
    - **include_replies**: Whether to include nested replies (default: true)
    - **limit**: Maximum number of comments to return (1-500)
    - **offset**: Number of comments to skip for pagination
    
    Returns comments in chronological order with optional nested replies.
    """
    try:
        service = CommentService(db)
        comments = await service.list_document_comments(
            document_id, 
            current_user,
            include_replies=include_replies,
            limit=limit,
            offset=offset
        )
        
        if include_replies:
            return [_to_comment_response(comment) for comment in comments]
        else:
            return [_to_comment_list_response(comment) for comment in comments]
            
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=e.message)
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)


@router.get("/comments/{comment_id}", response_model=CommentResponse)
async def get_comment(
    comment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific comment by ID.
    
    - **comment_id**: UUID of the comment to retrieve
    """
    try:
        service = CommentService(db)
        comment = await service.get_comment(comment_id, current_user)
        return _to_comment_response(comment)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=e.message)
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)


@router.put("/comments/{comment_id}", response_model=CommentResponse)
async def update_comment(
    comment_id: uuid.UUID,
    comment_data: CommentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update an existing comment.
    
    - **comment_id**: UUID of the comment to update
    - **content**: Updated comment content (required)
    
    Only the comment author or admin can update a comment.
    """
    try:
        service = CommentService(db)
        comment = await service.update_comment(comment_id, comment_data, current_user)
        return _to_comment_response(comment)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=e.message)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    comment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a comment (soft delete).
    
    - **comment_id**: UUID of the comment to delete
    
    Only the comment author or admin can delete a comment.
    The comment will be marked as deleted but preserved for audit purposes.
    """
    try:
        service = CommentService(db)
        await service.delete_comment(comment_id, current_user)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=e.message)
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)


def _to_comment_response(comment) -> CommentResponse:
    """Convert Comment model to CommentResponse schema with nested replies."""
    replies = []
    if hasattr(comment, 'replies') and comment.replies:
        replies = [_to_comment_response(reply) for reply in comment.replies]
    
    reply_count = getattr(comment, 'reply_count', len(replies))
    
    return CommentResponse(
        id=str(comment.id),
        content=comment.content,
        document_id=str(comment.document_id),
        author_id=str(comment.author_id),
        author_username=comment.author.username,
        parent_id=str(comment.parent_id) if comment.parent_id else None,
        is_deleted=comment.is_deleted,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        replies=replies,
        reply_count=reply_count
    )


def _to_comment_list_response(comment) -> CommentListResponse:
    """Convert Comment model to CommentListResponse schema without nested replies."""
    reply_count = getattr(comment, 'reply_count', 0)
    
    return CommentListResponse(
        id=str(comment.id),
        content=comment.content,
        document_id=str(comment.document_id),
        author_id=str(comment.author_id),
        author_username=comment.author.username,
        parent_id=str(comment.parent_id) if comment.parent_id else None,
        is_deleted=comment.is_deleted,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        reply_count=reply_count
    )