"""
Search API endpoints for full-text search and autocomplete functionality.
"""
import logging
from typing import List, Optional, Dict
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.rate_limit import limiter
from app.models.user import User
from app.models.document import DocumentStatus
from app.services.search import SearchService, SearchFilters
from app.schemas.search import SearchResultsSchema
from app.schemas.responses import ErrorResponse
from fastapi import Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/search", tags=["search"])


@router.get(
    "",
    response_model=SearchResultsSchema,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid search query"},
        401: {"model": ErrorResponse, "description": "Authentication required"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Search documents",
    description="Perform full-text search on documents with ranking, relevance, and filtering capabilities."
)
@limiter.limit("60/minute")  # Allow 60 searches per minute per user
async def search_documents(
    request: Request,
    q: str = Query(..., description="Search query", min_length=1, max_length=200),
    folder_path: Optional[str] = Query(None, description="Filter by folder path"),
    tags: Optional[str] = Query(None, description="Comma-separated list of tags to filter by"),
    status: Optional[DocumentStatus] = Query(None, description="Filter by document status"),
    limit: int = Query(20, description="Maximum number of results", ge=1, le=100),
    offset: int = Query(0, description="Number of results to skip", ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Search documents using PostgreSQL full-text search with ranking and relevance.
    
    Features:
    - Full-text search with ranking based on title and content relevance
    - Search result highlighting and snippet generation
    - Permission-based filtering (users only see documents they have access to)
    - Folder-based filtering
    - Tag-based filtering (AND logic for multiple tags)
    - Status-based filtering
    - Pagination support
    """
    try:
        # Parse tags if provided
        tag_list = None
        if tags:
            tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
        
        # Create search filters
        filters = SearchFilters(
            folder_path=folder_path,
            tags=tag_list,
            status=status
        )
        
        # Perform search
        search_service = SearchService(db)
        results = await search_service.search_documents(
            query=q,
            filters=filters,
            user=current_user,
            limit=limit,
            offset=offset
        )
        
        # Record search analytics
        await search_service.record_search_analytics(
            query=q,
            user=current_user,
            results_count=len(results.results),
            execution_time_ms=results.execution_time_ms,
            filters=filters
        )
        
        logger.info(
            f"Search performed: user={current_user.id}, query='{q}', "
            f"results={len(results.results)}, time={results.execution_time_ms:.2f}ms"
        )
        
        return results
        
    except ValueError as e:
        logger.warning(f"Invalid search query: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid search query: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search operation failed"
        )


@router.get(
    "/autocomplete",
    response_model=List[str],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Tag autocomplete",
    description="Get tag autocomplete suggestions with sub-100ms response time using trigram indexes."
)
@limiter.limit("100/minute")  # Allow 100 autocomplete requests per minute
async def autocomplete_tags(
    request: Request,
    q: str = Query(..., description="Partial tag name", min_length=1, max_length=50),
    limit: int = Query(10, description="Maximum number of suggestions", ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Provide tag autocomplete with sub-100ms response time using PostgreSQL trigram indexes.
    
    Features:
    - Trigram similarity matching for fuzzy search
    - Usage count-based ranking (popular tags first)
    - Prefix matching for exact matches
    - Optimized for performance with proper indexing
    """
    try:
        search_service = SearchService(db)
        suggestions = await search_service.autocomplete_tags(
            partial=q,
            user=current_user,
            limit=limit
        )
        
        return suggestions
        
    except Exception as e:
        logger.error(f"Autocomplete error: {e}")
        # Return empty list on error to maintain performance
        return []


@router.get(
    "/suggestions",
    response_model=List[str],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Search suggestions",
    description="Get search suggestions based on document content and user query patterns."
)
@limiter.limit("100/minute")  # Allow 100 suggestion requests per minute
async def get_search_suggestions(
    request: Request,
    q: str = Query(..., description="Partial search query", min_length=2, max_length=100),
    limit: int = Query(5, description="Maximum number of suggestions", ge=1, le=10),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get search suggestions based on document titles, content, and user query patterns.
    
    Features:
    - Content-based suggestions from document titles and text
    - Intelligent word extraction and completion
    - Ranking based on relevance and popularity
    - Fast response time with caching
    """
    try:
        search_service = SearchService(db)
        suggestions = await search_service.get_search_suggestions(
            query=q,
            user=current_user,
            limit=limit
        )
        
        return suggestions
        
    except Exception as e:
        logger.error(f"Search suggestions error: {e}")
        # Return empty list on error to maintain performance
        return []

@
router.get(
    "/analytics/performance",
    response_model=Dict,
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Admin access required"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Search performance metrics",
    description="Get search performance metrics for monitoring and optimization (admin only)."
)
async def get_search_performance_metrics(
    days: int = Query(7, description="Number of days to retrieve metrics for", ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get search performance metrics including execution times, search counts, and performance scores.
    
    Admin-only endpoint for monitoring search system performance and identifying optimization opportunities.
    """
    # Check admin permissions
    if current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    try:
        search_service = SearchService(db)
        metrics = await search_service.get_search_performance_metrics(days=days)
        
        return metrics
        
    except Exception as e:
        logger.error(f"Error getting search performance metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve performance metrics"
        )


@router.get(
    "/analytics/popular-queries",
    response_model=List[Dict],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Admin access required"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Popular search queries",
    description="Get popular search queries for analysis and content optimization (admin only)."
)
async def get_popular_search_queries(
    days: int = Query(7, description="Number of days to analyze", ge=1, le=30),
    limit: int = Query(20, description="Maximum number of queries to return", ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get popular search queries to understand user search patterns and identify content gaps.
    
    Admin-only endpoint for analyzing search behavior and optimizing content strategy.
    """
    # Check admin permissions
    if current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    try:
        search_service = SearchService(db)
        popular_queries = await search_service.get_popular_queries(days=days, limit=limit)
        
        return popular_queries
        
    except Exception as e:
        logger.error(f"Error getting popular search queries: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve popular queries"
        )