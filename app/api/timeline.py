"""
Timeline API endpoints for consolidated edit tracking and activity feeds.
"""
import uuid
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.services.timeline import TimelineService
from app.schemas.timeline import (
    TimelineEventType, TimelineResponse, DocumentTimelineResponse,
    UserActivityResponse
)
from app.core.exceptions import NotFoundError, InternalError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/timeline", tags=["timeline"])


@router.get("/", response_model=TimelineResponse)
async def get_global_timeline(
    limit: int = Query(50, ge=1, le=100, description="Maximum number of events to return"),
    offset: int = Query(0, ge=0, description="Number of events to skip"),
    event_types: Optional[str] = Query(None, description="Comma-separated list of event types to filter by"),
    start_date: Optional[datetime] = Query(None, description="Filter events after this date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="Filter events before this date (ISO format)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get global timeline of all activities with filtering and pagination.
    
    - **limit**: Maximum number of events to return (1-100)
    - **offset**: Number of events to skip for pagination
    - **event_types**: Comma-separated list of event types to filter by
    - **start_date**: Filter events after this date (ISO format)
    - **end_date**: Filter events before this date (ISO format)
    
    Returns activities in reverse chronological order (newest first).
    """
    try:
        # Parse event types if provided
        parsed_event_types = None
        if event_types:
            type_strings = [t.strip() for t in event_types.split(",") if t.strip()]
            parsed_event_types = []
            for type_str in type_strings:
                try:
                    parsed_event_types.append(TimelineEventType(type_str))
                except ValueError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid event type: {type_str}"
                    )
        
        service = TimelineService(db)
        timeline = await service.get_global_timeline(
            user=current_user,
            limit=limit,
            offset=offset,
            event_types=parsed_event_types,
            start_date=start_date,
            end_date=end_date
        )
        
        return timeline
        
    except HTTPException:
        raise
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)


@router.get("/documents/{document_id}", response_model=DocumentTimelineResponse)
async def get_document_timeline(
    document_id: uuid.UUID,
    limit: int = Query(100, ge=1, le=500, description="Maximum number of events to return"),
    offset: int = Query(0, ge=0, description="Number of events to skip"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get timeline for a specific document showing all changes and activities.
    
    - **document_id**: UUID of the document
    - **limit**: Maximum number of events to return (1-500)
    - **offset**: Number of events to skip for pagination
    
    Returns all activities related to the document in reverse chronological order.
    Only users with read access to the document can view its timeline.
    """
    try:
        service = TimelineService(db)
        timeline = await service.get_document_timeline(
            document_id=document_id,
            user=current_user,
            limit=limit,
            offset=offset
        )
        
        return timeline
        
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)


@router.get("/users/{user_id}/activity", response_model=UserActivityResponse)
async def get_user_activity(
    user_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200, description="Maximum number of events to return"),
    offset: int = Query(0, ge=0, description="Number of events to skip"),
    days: int = Query(30, ge=1, le=90, description="Number of days to look back"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get activity timeline for a specific user.
    
    - **user_id**: UUID of the user to get activity for
    - **limit**: Maximum number of events to return (1-200)
    - **offset**: Number of events to skip for pagination
    - **days**: Number of days to look back (1-90)
    
    Returns user's activities with summary statistics.
    Users can view their own activity, admins can view any user's activity.
    """
    try:
        # Check permissions - users can view their own activity, admins can view any
        if user_id != current_user.id and current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Can only view your own activity unless you are an admin"
            )
        
        service = TimelineService(db)
        activity = await service.get_user_activity(
            target_user_id=user_id,
            requesting_user=current_user,
            limit=limit,
            offset=offset,
            days=days
        )
        
        return activity
        
    except HTTPException:
        raise
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)


@router.get("/summary/recent", response_model=Dict[str, Any])
async def get_recent_activity_summary(
    hours: int = Query(24, ge=1, le=168, description="Number of hours to look back (max 1 week)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get recent activity summary for dashboard display.
    
    - **hours**: Number of hours to look back (1-168, max 1 week)
    
    Returns activity counts by type and recent events for dashboard widgets.
    """
    try:
        service = TimelineService(db)
        summary = await service.get_recent_activity_summary(
            user=current_user,
            hours=hours
        )
        
        return summary
        
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)


@router.get("/events/types", response_model=List[str])
async def get_event_types(
    current_user: User = Depends(get_current_user)
):
    """
    Get list of available timeline event types for filtering.
    
    Returns all possible event types that can be used in timeline filters.
    """
    return [event_type.value for event_type in TimelineEventType]