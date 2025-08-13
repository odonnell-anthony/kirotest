"""
Timeline service for consolidated edit tracking and activity feeds.
"""
import uuid
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import AuditLog
from app.models.document import Document
from app.models.user import User
from app.models.comment import Comment
from app.models.folder import Folder
from app.schemas.timeline import (
    TimelineEventType, TimelineEventResponse, TimelineResponse,
    DocumentTimelineResponse, UserActivityResponse
)
from app.core.exceptions import NotFoundError, InternalError

logger = logging.getLogger(__name__)


class TimelineService:
    """Service for managing timeline and activity tracking."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_global_timeline(
        self,
        user: User,
        limit: int = 50,
        offset: int = 0,
        event_types: Optional[List[TimelineEventType]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> TimelineResponse:
        """
        Get global timeline of all activities.
        
        Args:
            user: User requesting the timeline
            limit: Maximum number of events to return
            offset: Number of events to skip
            event_types: Filter by specific event types
            start_date: Filter events after this date
            end_date: Filter events before this date
            
        Returns:
            Timeline response with events and pagination info
            
        Raises:
            InternalError: If timeline retrieval fails
        """
        try:
            # Build base query
            stmt = (
                select(AuditLog)
                .options(selectinload(AuditLog.user))
                .order_by(desc(AuditLog.created_at))
            )
            
            # Apply filters
            conditions = []
            
            if event_types:
                event_type_values = [et.value for et in event_types]
                conditions.append(AuditLog.action.in_(event_type_values))
            
            if start_date:
                conditions.append(AuditLog.created_at >= start_date)
            
            if end_date:
                conditions.append(AuditLog.created_at <= end_date)
            
            # Only show events for documents the user can access
            # For now, we'll show all published documents and user's own drafts
            if user.role != "admin":
                # This is a simplified permission check
                # In a real implementation, you'd want more sophisticated permission filtering
                pass
            
            if conditions:
                stmt = stmt.where(and_(*conditions))
            
            # Get total count
            count_stmt = select(func.count(AuditLog.id))
            if conditions:
                count_stmt = count_stmt.where(and_(*conditions))
            
            count_result = await self.db.execute(count_stmt)
            total_count = count_result.scalar() or 0
            
            # Get paginated results
            stmt = stmt.limit(limit).offset(offset)
            result = await self.db.execute(stmt)
            audit_logs = result.scalars().all()
            
            # Convert to timeline events
            events = []
            for log in audit_logs:
                event = await self._audit_log_to_timeline_event(log)
                if event:
                    events.append(event)
            
            has_more = offset + len(events) < total_count
            next_offset = offset + len(events) if has_more else None
            
            return TimelineResponse(
                events=events,
                total_count=total_count,
                has_more=has_more,
                next_offset=next_offset
            )
            
        except Exception as e:
            logger.error(f"Error getting global timeline: {e}")
            raise InternalError("Failed to retrieve timeline")
    
    async def get_document_timeline(
        self,
        document_id: uuid.UUID,
        user: User,
        limit: int = 100,
        offset: int = 0
    ) -> DocumentTimelineResponse:
        """
        Get timeline for a specific document.
        
        Args:
            document_id: Document ID
            user: User requesting the timeline
            limit: Maximum number of events to return
            offset: Number of events to skip
            
        Returns:
            Document timeline response
            
        Raises:
            NotFoundError: If document not found
            InternalError: If timeline retrieval fails
        """
        try:
            # Verify document exists and user can access it
            document = await self._get_document_with_permission_check(document_id, user)
            
            # Get audit logs for this document
            stmt = (
                select(AuditLog)
                .where(AuditLog.resource_id == str(document_id))
                .options(selectinload(AuditLog.user))
                .order_by(desc(AuditLog.created_at))
                .limit(limit)
                .offset(offset)
            )
            
            result = await self.db.execute(stmt)
            audit_logs = result.scalars().all()
            
            # Get total count
            count_stmt = (
                select(func.count(AuditLog.id))
                .where(AuditLog.resource_id == str(document_id))
            )
            count_result = await self.db.execute(count_stmt)
            total_count = count_result.scalar() or 0
            
            # Convert to timeline events
            events = []
            for log in audit_logs:
                event = await self._audit_log_to_timeline_event(log)
                if event:
                    events.append(event)
            
            return DocumentTimelineResponse(
                document_id=str(document_id),
                document_title=document.title,
                events=events,
                total_count=total_count
            )
            
        except NotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error getting document timeline for {document_id}: {e}")
            raise InternalError("Failed to retrieve document timeline")
    
    async def get_user_activity(
        self,
        target_user_id: uuid.UUID,
        requesting_user: User,
        limit: int = 50,
        offset: int = 0,
        days: int = 30
    ) -> UserActivityResponse:
        """
        Get activity timeline for a specific user.
        
        Args:
            target_user_id: User ID to get activity for
            requesting_user: User requesting the activity
            limit: Maximum number of events to return
            offset: Number of events to skip
            days: Number of days to look back
            
        Returns:
            User activity response
            
        Raises:
            NotFoundError: If target user not found
            InternalError: If activity retrieval fails
        """
        try:
            # Get target user
            target_user = await self._get_user(target_user_id)
            
            # Calculate date range
            start_date = datetime.utcnow() - timedelta(days=days)
            
            # Get audit logs for this user
            stmt = (
                select(AuditLog)
                .where(
                    and_(
                        AuditLog.user_id == target_user_id,
                        AuditLog.created_at >= start_date
                    )
                )
                .options(selectinload(AuditLog.user))
                .order_by(desc(AuditLog.created_at))
                .limit(limit)
                .offset(offset)
            )
            
            result = await self.db.execute(stmt)
            audit_logs = result.scalars().all()
            
            # Get total count
            count_stmt = (
                select(func.count(AuditLog.id))
                .where(
                    and_(
                        AuditLog.user_id == target_user_id,
                        AuditLog.created_at >= start_date
                    )
                )
            )
            count_result = await self.db.execute(count_stmt)
            total_count = count_result.scalar() or 0
            
            # Get activity summary (event type counts)
            summary_stmt = (
                select(AuditLog.action, func.count(AuditLog.id))
                .where(
                    and_(
                        AuditLog.user_id == target_user_id,
                        AuditLog.created_at >= start_date
                    )
                )
                .group_by(AuditLog.action)
            )
            summary_result = await self.db.execute(summary_stmt)
            activity_summary = dict(summary_result.all())
            
            # Convert to timeline events
            events = []
            for log in audit_logs:
                event = await self._audit_log_to_timeline_event(log)
                if event:
                    events.append(event)
            
            return UserActivityResponse(
                user_id=str(target_user_id),
                user_username=target_user.username,
                events=events,
                total_count=total_count,
                activity_summary=activity_summary
            )
            
        except NotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error getting user activity for {target_user_id}: {e}")
            raise InternalError("Failed to retrieve user activity")
    
    async def get_recent_activity_summary(
        self,
        user: User,
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get recent activity summary for dashboard.
        
        Args:
            user: User requesting the summary
            hours: Number of hours to look back
            
        Returns:
            Activity summary with counts and recent events
            
        Raises:
            InternalError: If summary retrieval fails
        """
        try:
            start_time = datetime.utcnow() - timedelta(hours=hours)
            
            # Get activity counts by type
            stmt = (
                select(AuditLog.action, func.count(AuditLog.id))
                .where(AuditLog.created_at >= start_time)
                .group_by(AuditLog.action)
            )
            
            result = await self.db.execute(stmt)
            activity_counts = dict(result.all())
            
            # Get recent events
            recent_stmt = (
                select(AuditLog)
                .where(AuditLog.created_at >= start_time)
                .options(selectinload(AuditLog.user))
                .order_by(desc(AuditLog.created_at))
                .limit(10)
            )
            
            recent_result = await self.db.execute(recent_stmt)
            recent_logs = recent_result.scalars().all()
            
            recent_events = []
            for log in recent_logs:
                event = await self._audit_log_to_timeline_event(log)
                if event:
                    recent_events.append(event)
            
            return {
                "period_hours": hours,
                "activity_counts": activity_counts,
                "total_events": sum(activity_counts.values()),
                "recent_events": recent_events,
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting recent activity summary: {e}")
            raise InternalError("Failed to retrieve activity summary")
    
    async def _audit_log_to_timeline_event(self, log: AuditLog) -> Optional[TimelineEventResponse]:
        """Convert audit log to timeline event."""
        try:
            # Map audit actions to timeline event types
            action_mapping = {
                "create_document": TimelineEventType.DOCUMENT_CREATED,
                "update_document": TimelineEventType.DOCUMENT_UPDATED,
                "publish_document": TimelineEventType.DOCUMENT_PUBLISHED,
                "move_document": TimelineEventType.DOCUMENT_MOVED,
                "delete_document": TimelineEventType.DOCUMENT_DELETED,
                "create_comment": TimelineEventType.COMMENT_CREATED,
                "update_comment": TimelineEventType.COMMENT_UPDATED,
                "delete_comment": TimelineEventType.COMMENT_DELETED,
                "create_folder": TimelineEventType.FOLDER_CREATED,
                "update_folder": TimelineEventType.FOLDER_UPDATED,
                "move_folder": TimelineEventType.FOLDER_MOVED,
                "delete_folder": TimelineEventType.FOLDER_DELETED,
                "add_tag": TimelineEventType.TAG_ADDED,
                "remove_tag": TimelineEventType.TAG_REMOVED,
            }
            
            event_type = action_mapping.get(log.action)
            if not event_type:
                return None
            
            # Generate title and description based on event type
            title, description = self._generate_event_title_description(log, event_type)
            
            # Extract document info if available
            document_id = None
            document_title = None
            if log.resource_type == "document" and log.resource_id:
                document_id = log.resource_id
                # Try to get document title from metadata or fetch from DB
                if log.custom_metadata and "title" in log.custom_metadata:
                    document_title = log.custom_metadata["title"]
            
            return TimelineEventResponse(
                id=str(log.id),
                event_type=event_type,
                title=title,
                description=description,
                user_id=str(log.user_id),
                user_username=log.user.username if log.user else "Unknown",
                document_id=document_id,
                document_title=document_title,
                folder_path=log.custom_metadata.get("folder_path") if log.custom_metadata else None,
                metadata=log.custom_metadata or {},
                created_at=log.created_at
            )
            
        except Exception as e:
            logger.warning(f"Error converting audit log to timeline event: {e}")
            return None
    
    def _generate_event_title_description(self, log: AuditLog, event_type: TimelineEventType) -> tuple[str, str]:
        """Generate human-readable title and description for timeline event."""
        user_name = log.user.username if log.user else "Unknown user"
        
        if event_type == TimelineEventType.DOCUMENT_CREATED:
            title = f"{user_name} created a document"
            description = f"New document created"
        elif event_type == TimelineEventType.DOCUMENT_UPDATED:
            title = f"{user_name} updated a document"
            description = f"Document content was modified"
        elif event_type == TimelineEventType.DOCUMENT_PUBLISHED:
            title = f"{user_name} published a document"
            description = f"Document status changed to published"
        elif event_type == TimelineEventType.DOCUMENT_MOVED:
            title = f"{user_name} moved a document"
            description = f"Document was moved to a different folder"
        elif event_type == TimelineEventType.DOCUMENT_DELETED:
            title = f"{user_name} deleted a document"
            description = f"Document was removed"
        elif event_type == TimelineEventType.COMMENT_CREATED:
            title = f"{user_name} added a comment"
            description = f"New comment posted on document"
        elif event_type == TimelineEventType.COMMENT_UPDATED:
            title = f"{user_name} edited a comment"
            description = f"Comment content was modified"
        elif event_type == TimelineEventType.COMMENT_DELETED:
            title = f"{user_name} deleted a comment"
            description = f"Comment was removed"
        elif event_type == TimelineEventType.FOLDER_CREATED:
            title = f"{user_name} created a folder"
            description = f"New folder created for organization"
        elif event_type == TimelineEventType.FOLDER_UPDATED:
            title = f"{user_name} updated a folder"
            description = f"Folder details were modified"
        elif event_type == TimelineEventType.FOLDER_MOVED:
            title = f"{user_name} moved a folder"
            description = f"Folder was moved to a different location"
        elif event_type == TimelineEventType.FOLDER_DELETED:
            title = f"{user_name} deleted a folder"
            description = f"Folder was removed"
        elif event_type == TimelineEventType.TAG_ADDED:
            title = f"{user_name} added a tag"
            description = f"Tag was added to document"
        elif event_type == TimelineEventType.TAG_REMOVED:
            title = f"{user_name} removed a tag"
            description = f"Tag was removed from document"
        else:
            title = f"{user_name} performed an action"
            description = f"Activity recorded"
        
        # Add specific details from metadata if available
        if log.custom_metadata:
            if "title" in log.custom_metadata:
                title += f": {log.custom_metadata['title']}"
            if "change_summary" in log.custom_metadata:
                description = log.custom_metadata["change_summary"]
        
        return title, description
    
    async def _get_document_with_permission_check(self, document_id: uuid.UUID, user: User) -> Document:
        """Get document and check if user can access it."""
        stmt = select(Document).where(Document.id == document_id)
        result = await self.db.execute(stmt)
        document = result.scalar_one_or_none()
        
        if not document:
            raise NotFoundError(f"Document with ID {document_id} not found")
        
        # Check if user can read the document
        if document.status == "draft":
            if document.author_id != user.id and user.role != "admin":
                raise NotFoundError(f"Document with ID {document_id} not found")
        
        return document
    
    async def _get_user(self, user_id: uuid.UUID) -> User:
        """Get user by ID."""
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            raise NotFoundError(f"User with ID {user_id} not found")
        
        return user    
async def get_recent_activity(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent activity for dashboard display."""
        try:
            # Get recent audit log entries
            result = await self.db.execute(
                select(AuditLog)
                .options(selectinload(AuditLog.user))
                .where(AuditLog.resource_type == 'document')
                .order_by(AuditLog.created_at.desc())
                .limit(limit)
            )
            audit_logs = result.scalars().all()
            
            activities = []
            for log in audit_logs:
                # Get document info if available
                document_title = log.resource_id
                document_path = None
                
                if log.resource_id:
                    try:
                        doc_result = await self.db.execute(
                            select(Document).where(Document.id == uuid.UUID(log.resource_id))
                        )
                        document = doc_result.scalar_one_or_none()
                        if document:
                            document_title = document.title
                            document_path = f"/{document.slug}"
                    except (ValueError, Exception):
                        pass
                
                activities.append({
                    "action": log.action,
                    "document_title": document_title,
                    "document_path": document_path,
                    "author_name": log.user.username if log.user else "Unknown",
                    "created_at": log.created_at,
                    "summary": log.details.get("summary") if log.details else None
                })
            
            return activities
            
        except Exception as e:
            logger.error(f"Error getting recent activity: {e}")
            return []