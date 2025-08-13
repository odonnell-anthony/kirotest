"""
Tag management service.
"""
import uuid
import logging
import time
from typing import List, Optional, Dict, Any
from sqlalchemy import select, update, delete, func, text, and_, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tag import Tag, DocumentTag
from app.models.document import Document
from app.models.user import User
from app.schemas.tag import (
    TagCreate, TagUpdate, TagResponse, TagSuggestion, 
    TagUsageInfo, TagRenameRequest, TagDeleteResponse,
    TagAutocompleteResponse
)
from app.core.database import get_db_session
from app.core.exceptions import ValidationError, NotFoundError, ConflictError
from app.core.redis import get_redis

logger = logging.getLogger(__name__)


class TagService:
    """Service for managing tags and tag operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_tag(self, tag_data: TagCreate, user: User) -> TagResponse:
        """
        Create a new tag.
        
        Args:
            tag_data: Tag creation data
            user: User creating the tag
            
        Returns:
            TagResponse: Created tag information
            
        Raises:
            ConflictError: If tag name already exists
            ValidationError: If tag data is invalid
        """
        try:
            # Check if tag already exists
            existing_tag = await self._get_tag_by_name(tag_data.name)
            if existing_tag:
                raise ConflictError(f"Tag '{tag_data.name}' already exists")
            
            # Create new tag
            tag = Tag(
                name=tag_data.name,
                description=tag_data.description,
                color=tag_data.color,
                usage_count=0
            )
            
            self.db.add(tag)
            await self.db.commit()
            await self.db.refresh(tag)
            
            logger.info(f"Tag '{tag.name}' created by user {user.id}")
            
            # Clear autocomplete cache
            await self._clear_autocomplete_cache()
            
            return TagResponse.from_orm(tag)
            
        except Exception as e:
            await self.db.rollback()
            if isinstance(e, (ConflictError, ValidationError)):
                raise
            logger.error(f"Error creating tag: {e}")
            raise ValidationError("Failed to create tag")
    
    async def get_tag(self, tag_id: uuid.UUID) -> TagResponse:
        """
        Get a tag by ID.
        
        Args:
            tag_id: Tag ID
            
        Returns:
            TagResponse: Tag information
            
        Raises:
            NotFoundError: If tag not found
        """
        tag = await self._get_tag_by_id(tag_id)
        if not tag:
            raise NotFoundError(f"Tag with ID {tag_id} not found")
        
        return TagResponse.from_orm(tag)
    
    async def get_tag_by_name(self, name: str) -> Optional[TagResponse]:
        """
        Get a tag by name.
        
        Args:
            name: Tag name
            
        Returns:
            Optional[TagResponse]: Tag information if found
        """
        tag = await self._get_tag_by_name(name)
        if tag:
            return TagResponse.from_orm(tag)
        return None
    
    async def list_tags(
        self, 
        limit: int = 100, 
        offset: int = 0,
        sort_by: str = "usage_count",
        sort_order: str = "desc",
        search: Optional[str] = None
    ) -> List[TagResponse]:
        """
        List all tags with optional filtering and sorting.
        
        Args:
            limit: Maximum number of tags to return
            offset: Number of tags to skip
            sort_by: Field to sort by (name, usage_count, created_at)
            sort_order: Sort order (asc, desc)
            search: Optional search term
            
        Returns:
            List[TagResponse]: List of tags
        """
        try:
            query = select(Tag)
            
            # Apply search filter
            if search:
                search_term = f"%{search.lower()}%"
                query = query.where(
                    or_(
                        Tag.name.ilike(search_term),
                        Tag.description.ilike(search_term)
                    )
                )
            
            # Apply sorting
            if sort_by == "name":
                sort_column = Tag.name
            elif sort_by == "created_at":
                sort_column = Tag.created_at
            else:  # default to usage_count
                sort_column = Tag.usage_count
            
            if sort_order.lower() == "asc":
                query = query.order_by(sort_column.asc())
            else:
                query = query.order_by(sort_column.desc())
            
            # Apply pagination
            query = query.offset(offset).limit(limit)
            
            result = await self.db.execute(query)
            tags = result.scalars().all()
            
            return [TagResponse.from_orm(tag) for tag in tags]
            
        except Exception as e:
            logger.error(f"Error listing tags: {e}")
            return []
    
    async def update_tag(
        self, 
        tag_id: uuid.UUID, 
        tag_data: TagUpdate, 
        user: User
    ) -> TagResponse:
        """
        Update an existing tag.
        
        Args:
            tag_id: Tag ID to update
            tag_data: Updated tag data
            user: User performing the update
            
        Returns:
            TagResponse: Updated tag information
            
        Raises:
            NotFoundError: If tag not found
            ConflictError: If new name conflicts with existing tag
        """
        try:
            tag = await self._get_tag_by_id(tag_id)
            if not tag:
                raise NotFoundError(f"Tag with ID {tag_id} not found")
            
            # Check for name conflicts if name is being changed
            if tag_data.name and tag_data.name != tag.name:
                existing_tag = await self._get_tag_by_name(tag_data.name)
                if existing_tag:
                    raise ConflictError(f"Tag '{tag_data.name}' already exists")
            
            # Update fields
            update_data = tag_data.dict(exclude_unset=True)
            for field, value in update_data.items():
                setattr(tag, field, value)
            
            await self.db.commit()
            await self.db.refresh(tag)
            
            logger.info(f"Tag {tag_id} updated by user {user.id}")
            
            # Clear autocomplete cache
            await self._clear_autocomplete_cache()
            
            return TagResponse.from_orm(tag)
            
        except Exception as e:
            await self.db.rollback()
            if isinstance(e, (NotFoundError, ConflictError)):
                raise
            logger.error(f"Error updating tag: {e}")
            raise ValidationError("Failed to update tag")
    
    async def rename_tag(
        self, 
        rename_request: TagRenameRequest, 
        user: User
    ) -> TagResponse:
        """
        Rename a tag with cascading updates to all associated documents.
        
        Args:
            rename_request: Tag rename request data
            user: User performing the rename
            
        Returns:
            TagResponse: Updated tag information
            
        Raises:
            NotFoundError: If old tag not found
            ConflictError: If new name conflicts with existing tag
        """
        try:
            # Find the tag to rename
            old_tag = await self._get_tag_by_name(rename_request.old_name)
            if not old_tag:
                raise NotFoundError(f"Tag '{rename_request.old_name}' not found")
            
            # Check if new name conflicts
            if rename_request.old_name != rename_request.new_name:
                existing_tag = await self._get_tag_by_name(rename_request.new_name)
                if existing_tag:
                    raise ConflictError(f"Tag '{rename_request.new_name}' already exists")
            
            # Update the tag name
            old_tag.name = rename_request.new_name
            
            await self.db.commit()
            await self.db.refresh(old_tag)
            
            logger.info(
                f"Tag renamed from '{rename_request.old_name}' to '{rename_request.new_name}' "
                f"by user {user.id}"
            )
            
            # Clear autocomplete cache
            await self._clear_autocomplete_cache()
            
            return TagResponse.from_orm(old_tag)
            
        except Exception as e:
            await self.db.rollback()
            if isinstance(e, (NotFoundError, ConflictError)):
                raise
            logger.error(f"Error renaming tag: {e}")
            raise ValidationError("Failed to rename tag")
    
    async def delete_tag(
        self, 
        tag_id: uuid.UUID, 
        user: User,
        force: bool = False
    ) -> TagDeleteResponse:
        """
        Delete a tag with usage validation.
        
        Args:
            tag_id: Tag ID to delete
            user: User performing the deletion
            force: Whether to force deletion even if tag is in use
            
        Returns:
            TagDeleteResponse: Deletion result information
            
        Raises:
            NotFoundError: If tag not found
            ValidationError: If tag is in use and force=False
        """
        try:
            tag = await self._get_tag_by_id(tag_id)
            if not tag:
                raise NotFoundError(f"Tag with ID {tag_id} not found")
            
            # Check usage count
            usage_info = await self.get_tag_usage_info(tag_id)
            
            if usage_info.document_count > 0 and not force:
                raise ValidationError(
                    f"Tag '{tag.name}' is used by {usage_info.document_count} documents. "
                    f"Use force=True to delete anyway."
                )
            
            # Delete the tag (cascading will handle document_tags)
            await self.db.delete(tag)
            await self.db.commit()
            
            logger.info(
                f"Tag '{tag.name}' deleted by user {user.id}, "
                f"affected {usage_info.document_count} documents"
            )
            
            # Clear autocomplete cache
            await self._clear_autocomplete_cache()
            
            return TagDeleteResponse(
                success=True,
                message=f"Tag '{tag.name}' deleted successfully",
                affected_documents=usage_info.document_count
            )
            
        except Exception as e:
            await self.db.rollback()
            if isinstance(e, (NotFoundError, ValidationError)):
                raise
            logger.error(f"Error deleting tag: {e}")
            raise ValidationError("Failed to delete tag")
    
    async def get_tag_usage_info(self, tag_id: uuid.UUID) -> TagUsageInfo:
        """
        Get detailed usage information for a tag.
        
        Args:
            tag_id: Tag ID
            
        Returns:
            TagUsageInfo: Tag usage information
            
        Raises:
            NotFoundError: If tag not found
        """
        tag = await self._get_tag_by_id(tag_id)
        if not tag:
            raise NotFoundError(f"Tag with ID {tag_id} not found")
        
        # Get recent documents using this tag
        query = select(Document.title).join(
            DocumentTag, Document.id == DocumentTag.document_id
        ).where(
            DocumentTag.tag_id == tag_id
        ).order_by(
            Document.updated_at.desc()
        ).limit(5)
        
        result = await self.db.execute(query)
        recent_documents = [row[0] for row in result.fetchall()]
        
        return TagUsageInfo(
            tag_id=tag.id,
            tag_name=tag.name,
            document_count=tag.usage_count,
            recent_documents=recent_documents
        )
    
    async def suggest_tags(
        self, 
        content: str, 
        existing_tags: List[str] = None,
        limit: int = 10
    ) -> List[TagSuggestion]:
        """
        Suggest tags for content based on existing tags and content analysis.
        
        Args:
            content: Document content to analyze
            existing_tags: Tags already assigned to the document
            limit: Maximum number of suggestions
            
        Returns:
            List[TagSuggestion]: List of tag suggestions
        """
        try:
            existing_tags = existing_tags or []
            suggestions = []
            
            # Get popular tags that might be relevant
            query = select(Tag).where(
                and_(
                    Tag.usage_count > 0,
                    ~Tag.name.in_(existing_tags) if existing_tags else True
                )
            ).order_by(Tag.usage_count.desc()).limit(limit * 2)
            
            result = await self.db.execute(query)
            popular_tags = result.scalars().all()
            
            # Simple content-based suggestion (can be enhanced with NLP)
            content_lower = content.lower()
            
            for tag in popular_tags:
                # Check if tag name appears in content
                if tag.name.lower() in content_lower:
                    suggestions.append(TagSuggestion(
                        name=tag.name,
                        usage_count=tag.usage_count,
                        similarity_score=1.0
                    ))
                elif len(suggestions) < limit // 2:
                    # Add some popular tags even if not directly mentioned
                    suggestions.append(TagSuggestion(
                        name=tag.name,
                        usage_count=tag.usage_count,
                        similarity_score=0.5
                    ))
            
            # Sort by similarity score and usage count
            suggestions.sort(key=lambda x: (x.similarity_score or 0, x.usage_count), reverse=True)
            
            return suggestions[:limit]
            
        except Exception as e:
            logger.error(f"Error suggesting tags: {e}")
            return []
    
    async def autocomplete_tags(
        self, 
        partial: str, 
        limit: int = 10
    ) -> TagAutocompleteResponse:
        """
        Provide tag autocomplete with sub-100ms response time.
        
        Args:
            partial: Partial tag name
            limit: Maximum number of suggestions
            
        Returns:
            TagAutocompleteResponse: Autocomplete response with timing
        """
        start_time = time.time()
        
        try:
            # Sanitize input
            if not partial or len(partial.strip()) == 0:
                return TagAutocompleteResponse(
                    suggestions=[],
                    total_count=0,
                    query_time_ms=0.0
                )
            
            sanitized_partial = partial.strip().lower()
            
            # Check cache first
            redis = await get_redis()
            cache_key = f"autocomplete:tags:{sanitized_partial}:{limit}"
            
            if redis:
                cached_result = await redis.get(cache_key)
                if cached_result:
                    import json
                    cached_data = json.loads(cached_result)
                    return TagAutocompleteResponse(**cached_data)
            
            # Use trigram similarity for fast autocomplete
            query = text("""
                SELECT t.name, t.usage_count,
                       similarity(t.name, :partial) as sim
                FROM tags t
                WHERE t.name % :partial
                   OR t.name ILIKE :partial_like
                ORDER BY sim DESC, t.usage_count DESC, t.name ASC
                LIMIT :limit
            """)
            
            result = await self.db.execute(
                query,
                {
                    "partial": sanitized_partial,
                    "partial_like": f"{sanitized_partial}%",
                    "limit": limit
                }
            )
            
            suggestions = []
            for row in result.fetchall():
                suggestions.append(TagSuggestion(
                    name=row[0],
                    usage_count=row[1],
                    similarity_score=row[2] if len(row) > 2 else None
                ))
            
            # Get total count for pagination info
            count_query = text("""
                SELECT COUNT(*)
                FROM tags t
                WHERE t.name % :partial
                   OR t.name ILIKE :partial_like
            """)
            
            count_result = await self.db.execute(
                count_query,
                {
                    "partial": sanitized_partial,
                    "partial_like": f"{sanitized_partial}%"
                }
            )
            total_count = count_result.scalar()
            
            query_time_ms = (time.time() - start_time) * 1000
            
            response = TagAutocompleteResponse(
                suggestions=suggestions,
                total_count=total_count,
                query_time_ms=query_time_ms
            )
            
            # Cache results for 5 minutes
            if redis:
                await redis.setex(
                    cache_key, 
                    300,  # 5 minutes
                    response.json()
                )
            
            return response
            
        except Exception as e:
            query_time_ms = (time.time() - start_time) * 1000
            logger.error(f"Error in tag autocomplete: {e}")
            return TagAutocompleteResponse(
                suggestions=[],
                total_count=0,
                query_time_ms=query_time_ms
            )
    
    async def update_tag_usage_counts(self) -> Dict[str, int]:
        """
        Update usage counts for all tags based on current document associations.
        
        Returns:
            Dict[str, int]: Updated tag counts
        """
        try:
            # Update usage counts using a single query
            update_query = text("""
                UPDATE tags 
                SET usage_count = (
                    SELECT COUNT(*)
                    FROM document_tags dt
                    WHERE dt.tag_id = tags.id
                )
            """)
            
            await self.db.execute(update_query)
            await self.db.commit()
            
            # Get updated counts
            query = select(Tag.name, Tag.usage_count)
            result = await self.db.execute(query)
            
            updated_counts = {row[0]: row[1] for row in result.fetchall()}
            
            logger.info(f"Updated usage counts for {len(updated_counts)} tags")
            
            return updated_counts
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating tag usage counts: {e}")
            return {}
    
    # Private helper methods
    
    async def _get_tag_by_id(self, tag_id: uuid.UUID) -> Optional[Tag]:
        """Get tag by ID."""
        query = select(Tag).where(Tag.id == tag_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def _get_tag_by_name(self, name: str) -> Optional[Tag]:
        """Get tag by name."""
        query = select(Tag).where(Tag.name == name.lower())
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def _clear_autocomplete_cache(self):
        """Clear autocomplete cache."""
        try:
            redis = await get_redis()
            if redis:
                # Clear all autocomplete cache entries
                keys = await redis.keys("autocomplete:tags:*")
                if keys:
                    await redis.delete(*keys)
        except Exception as e:
            logger.warning(f"Failed to clear autocomplete cache: {e}")


# Dependency injection helper
async def get_tag_service() -> TagService:
    """Get tag service instance."""
    async with get_db_session() as db:
        return TagService(db)    
async def get_all_tags(self) -> List[Tag]:
        """Get all tags."""
        try:
            result = await self.db.execute(
                select(Tag).order_by(Tag.name)
            )
            tags = result.scalars().all()
            return list(tags)
            
        except Exception as e:
            logger.error(f"Error getting all tags: {e}")
            raise
    
    async def get_tag_count(self) -> int:
        """Get total number of tags."""
        try:
            result = await self.db.execute(
                select(func.count(Tag.id))
            )
            count = result.scalar() or 0
            return count
            
        except Exception as e:
            logger.error(f"Error getting tag count: {e}")
            return 0
    
    async def get_popular_tags(self, limit: int = 20) -> List[Tag]:
        """Get most popular tags by usage count."""
        try:
            result = await self.db.execute(
                select(Tag)
                .where(Tag.usage_count > 0)
                .order_by(Tag.usage_count.desc())
                .limit(limit)
            )
            tags = result.scalars().all()
            return list(tags)
            
        except Exception as e:
            logger.error(f"Error getting popular tags: {e}")
            return []