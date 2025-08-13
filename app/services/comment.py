"""
Comment service for document discussions.
"""
import uuid
import logging
from typing import List, Optional
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.comment import Comment
from app.models.document import Document
from app.models.user import User
from app.schemas.comment import CommentCreate, CommentUpdate
from app.core.exceptions import (
    NotFoundError, PermissionDeniedError, ValidationError, InternalError
)

logger = logging.getLogger(__name__)


class CommentService:
    """Service for managing comment operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_comment(
        self, 
        document_id: uuid.UUID, 
        comment_data: CommentCreate, 
        user: User
    ) -> Comment:
        """
        Create a new comment on a document.
        
        Args:
            document_id: Document ID
            comment_data: Comment creation data
            user: User creating the comment
            
        Returns:
            Created comment
            
        Raises:
            NotFoundError: If document or parent comment not found
            ValidationError: If comment data is invalid
            InternalError: If creation fails
        """
        try:
            # Verify document exists and user can read it
            document = await self._get_document_with_permission_check(document_id, user)
            
            # Verify parent comment exists if specified
            parent_comment = None
            if comment_data.parent_id:
                parent_comment = await self._get_comment(comment_data.parent_id)
                if parent_comment.document_id != document_id:
                    raise ValidationError("Parent comment must be on the same document")
            
            # Create comment
            comment = Comment(
                content=comment_data.content,
                document_id=document_id,
                author_id=user.id,
                parent_id=comment_data.parent_id
            )
            
            self.db.add(comment)
            await self.db.commit()
            await self.db.refresh(comment, ['author'])
            
            logger.info(f"Created comment on document {document_id} by user {user.username}")
            return comment
            
        except (NotFoundError, ValidationError):
            await self.db.rollback()
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating comment: {e}")
            raise InternalError("Failed to create comment")
    
    async def get_comment(self, comment_id: uuid.UUID, user: User) -> Comment:
        """
        Get a comment by ID.
        
        Args:
            comment_id: Comment ID
            user: User requesting the comment
            
        Returns:
            Comment instance
            
        Raises:
            NotFoundError: If comment not found
            PermissionDeniedError: If user lacks permission
            InternalError: If retrieval fails
        """
        try:
            comment = await self._get_comment(comment_id)
            
            # Check if user can read the document
            await self._get_document_with_permission_check(comment.document_id, user)
            
            return comment
            
        except (NotFoundError, PermissionDeniedError):
            raise
        except Exception as e:
            logger.error(f"Error getting comment {comment_id}: {e}")
            raise InternalError("Failed to retrieve comment")
    
    async def list_document_comments(
        self, 
        document_id: uuid.UUID, 
        user: User,
        include_replies: bool = True,
        limit: int = 100,
        offset: int = 0
    ) -> List[Comment]:
        """
        List comments for a document.
        
        Args:
            document_id: Document ID
            user: User requesting the comments
            include_replies: Whether to include nested replies
            limit: Maximum number of comments to return
            offset: Number of comments to skip
            
        Returns:
            List of comments
            
        Raises:
            NotFoundError: If document not found
            PermissionDeniedError: If user lacks permission
            InternalError: If listing fails
        """
        try:
            # Check if user can read the document
            await self._get_document_with_permission_check(document_id, user)
            
            if include_replies:
                # Get all comments with nested structure
                return await self._get_comments_with_replies(document_id, limit, offset)
            else:
                # Get top-level comments only
                stmt = (
                    select(Comment)
                    .where(
                        and_(
                            Comment.document_id == document_id,
                            Comment.parent_id.is_(None),
                            Comment.is_deleted == False
                        )
                    )
                    .options(selectinload(Comment.author))
                    .order_by(Comment.created_at)
                    .limit(limit)
                    .offset(offset)
                )
                
                result = await self.db.execute(stmt)
                comments = result.scalars().all()
                
                # Add reply counts
                for comment in comments:
                    comment.reply_count = await self._get_reply_count(comment.id)
                
                return list(comments)
            
        except (NotFoundError, PermissionDeniedError):
            raise
        except Exception as e:
            logger.error(f"Error listing comments for document {document_id}: {e}")
            raise InternalError("Failed to list comments")
    
    async def update_comment(
        self, 
        comment_id: uuid.UUID, 
        comment_data: CommentUpdate, 
        user: User
    ) -> Comment:
        """
        Update an existing comment.
        
        Args:
            comment_id: Comment ID
            comment_data: Update data
            user: User performing the update
            
        Returns:
            Updated comment
            
        Raises:
            NotFoundError: If comment not found
            PermissionDeniedError: If user lacks permission
            ValidationError: If update data is invalid
            InternalError: If update fails
        """
        try:
            comment = await self._get_comment(comment_id)
            
            # Check permissions (only author or admin can update)
            if comment.author_id != user.id and user.role != "admin":
                raise PermissionDeniedError("Only comment author or admin can update comment")
            
            # Check if user can read the document
            await self._get_document_with_permission_check(comment.document_id, user)
            
            # Update comment
            comment.content = comment_data.content
            
            await self.db.commit()
            await self.db.refresh(comment, ['author'])
            
            logger.info(f"Updated comment {comment_id} by user {user.username}")
            return comment
            
        except (NotFoundError, PermissionDeniedError, ValidationError):
            await self.db.rollback()
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating comment {comment_id}: {e}")
            raise InternalError("Failed to update comment")
    
    async def delete_comment(self, comment_id: uuid.UUID, user: User) -> None:
        """
        Delete a comment (soft delete).
        
        Args:
            comment_id: Comment ID
            user: User performing the deletion
            
        Raises:
            NotFoundError: If comment not found
            PermissionDeniedError: If user lacks permission
            InternalError: If deletion fails
        """
        try:
            comment = await self._get_comment(comment_id)
            
            # Check permissions (only author or admin can delete)
            if comment.author_id != user.id and user.role != "admin":
                raise PermissionDeniedError("Only comment author or admin can delete comment")
            
            # Check if user can read the document
            await self._get_document_with_permission_check(comment.document_id, user)
            
            # Soft delete
            comment.is_deleted = True
            comment.content = "[Comment deleted]"
            
            await self.db.commit()
            
            logger.info(f"Deleted comment {comment_id} by user {user.username}")
            
        except (NotFoundError, PermissionDeniedError):
            await self.db.rollback()
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting comment {comment_id}: {e}")
            raise InternalError("Failed to delete comment")
    
    async def _get_comment(self, comment_id: uuid.UUID) -> Comment:
        """Get comment by ID with author loaded."""
        stmt = (
            select(Comment)
            .where(Comment.id == comment_id)
            .options(selectinload(Comment.author))
        )
        result = await self.db.execute(stmt)
        comment = result.scalar_one_or_none()
        
        if not comment:
            raise NotFoundError(f"Comment with ID {comment_id} not found")
        
        return comment
    
    async def _get_document_with_permission_check(self, document_id: uuid.UUID, user: User) -> Document:
        """Get document and check if user can read it."""
        stmt = select(Document).where(Document.id == document_id)
        result = await self.db.execute(stmt)
        document = result.scalar_one_or_none()
        
        if not document:
            raise NotFoundError(f"Document with ID {document_id} not found")
        
        # Check if user can read the document
        # Published documents are visible to all users
        # Draft documents are only visible to their authors and admins
        if document.status == "draft":
            if document.author_id != user.id and user.role != "admin":
                raise PermissionDeniedError("Cannot access draft document")
        
        return document
    
    async def _get_comments_with_replies(
        self, 
        document_id: uuid.UUID, 
        limit: int, 
        offset: int
    ) -> List[Comment]:
        """Get comments with nested replies structure."""
        # Get all comments for the document
        stmt = (
            select(Comment)
            .where(
                and_(
                    Comment.document_id == document_id,
                    Comment.is_deleted == False
                )
            )
            .options(selectinload(Comment.author))
            .order_by(Comment.created_at)
        )
        
        result = await self.db.execute(stmt)
        all_comments = result.scalars().all()
        
        # Build comment map
        comment_map = {comment.id: comment for comment in all_comments}
        
        # Build nested structure
        root_comments = []
        for comment in all_comments:
            comment.replies = []
            comment.reply_count = 0
            
            if comment.parent_id is None:
                root_comments.append(comment)
            elif comment.parent_id in comment_map:
                parent = comment_map[comment.parent_id]
                parent.replies.append(comment)
                parent.reply_count += 1
        
        # Apply pagination to root comments only
        paginated_roots = root_comments[offset:offset + limit]
        
        return paginated_roots
    
    async def _get_reply_count(self, comment_id: uuid.UUID) -> int:
        """Get count of replies for a comment."""
        stmt = (
            select(func.count(Comment.id))
            .where(
                and_(
                    Comment.parent_id == comment_id,
                    Comment.is_deleted == False
                )
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0