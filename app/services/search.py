"""
Search service for high-performance full-text search and autocomplete functionality.
"""
import uuid
import logging
import re
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, text, desc
from sqlalchemy.orm import selectinload, joinedload
from redis.asyncio import Redis

from app.models.document import Document, DocumentStatus
from app.models.tag import Tag, DocumentTag
from app.models.user import User
from app.core.exceptions import ValidationError, InternalError
from app.core.redis import get_redis

logger = logging.getLogger(__name__)


@dataclass
class SearchFilters:
    """Search filters for document search."""
    folder_path: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[DocumentStatus] = None
    author_id: Optional[uuid.UUID] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None


@dataclass
class SearchResult:
    """Individual search result with highlighting and metadata."""
    document_id: uuid.UUID
    title: str
    slug: str
    folder_path: str
    content_snippet: str
    highlighted_title: str
    highlighted_snippet: str
    rank: float
    tags: List[str]
    author_name: str
    updated_at: str
    status: str


@dataclass
class SearchResults:
    """Search results container with metadata."""
    results: List[SearchResult]
    total_count: int
    query: str
    filters: SearchFilters
    execution_time_ms: float


class SearchService:
    """Service for high-performance search functionality."""
    
    def __init__(self, db: AsyncSession, redis: Optional[Redis] = None):
        self.db = db
        self.redis = redis or get_redis()
        self.cache_ttl = 300  # 5 minutes cache for search results
        self.autocomplete_cache_ttl = 3600  # 1 hour cache for autocomplete
    
    async def search_documents(
        self, 
        query: str, 
        filters: SearchFilters, 
        user: User,
        limit: int = 20,
        offset: int = 0
    ) -> SearchResults:
        """
        Perform full-text search on documents with ranking and relevance.
        
        Args:
            query: Search query string
            filters: Search filters
            user: User performing the search
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            SearchResults: Search results with metadata
            
        Raises:
            ValidationError: If search query is invalid
            InternalError: If search fails
        """
        import time
        start_time = time.time()
        
        try:
            # Validate and sanitize query
            sanitized_query = self._sanitize_search_query(query)
            if not sanitized_query:
                return SearchResults(
                    results=[],
                    total_count=0,
                    query=query,
                    filters=filters,
                    execution_time_ms=0.0
                )
            
            # Check cache first
            cache_key = self._generate_cache_key(sanitized_query, filters, user.id, limit, offset)
            cached_result = await self._get_cached_search_result(cache_key)
            if cached_result:
                cached_result.execution_time_ms = (time.time() - start_time) * 1000
                return cached_result
            
            # Build search query with PostgreSQL full-text search
            search_query = self._build_search_query(sanitized_query, filters, user)
            
            # Execute search with ranking
            result = await self.db.execute(search_query.limit(limit).offset(offset))
            search_rows = result.fetchall()
            
            # Get total count
            count_query = self._build_count_query(sanitized_query, filters, user)
            count_result = await self.db.execute(count_query)
            total_count = count_result.scalar()
            
            # Process results with highlighting
            search_results = []
            for row in search_rows:
                search_result = await self._process_search_result(row, sanitized_query)
                search_results.append(search_result)
            
            # Create results object
            results = SearchResults(
                results=search_results,
                total_count=total_count,
                query=query,
                filters=filters,
                execution_time_ms=(time.time() - start_time) * 1000
            )
            
            # Cache results
            await self._cache_search_result(cache_key, results)
            
            logger.info(f"Search completed: query='{query}', results={len(search_results)}, time={results.execution_time_ms:.2f}ms")
            return results
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error performing search: {e}")
            raise InternalError("Search operation failed")
    
    async def autocomplete_tags(
        self, 
        partial: str, 
        user: User,
        limit: int = 10
    ) -> List[str]:
        """
        Provide tag autocomplete with sub-100ms response time using trigram indexes.
        
        Args:
            partial: Partial tag name
            user: User requesting autocomplete
            limit: Maximum number of suggestions
            
        Returns:
            List[str]: List of matching tag names
        """
        try:
            # Validate input
            if not partial or len(partial.strip()) < 1:
                return []
            
            sanitized_partial = partial.strip().lower()
            
            # Check cache first
            cache_key = f"autocomplete:tags:{sanitized_partial}:{limit}"
            cached_tags = await self._get_cached_autocomplete(cache_key)
            if cached_tags is not None:
                return cached_tags
            
            # Use trigram similarity for fast autocomplete
            query = text("""
                SELECT t.name, 
                       similarity(t.name, :partial) as sim,
                       t.usage_count
                FROM tags t
                WHERE t.name % :partial
                   OR t.name ILIKE :partial_like
                ORDER BY sim DESC, t.usage_count DESC, t.name
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
            
            tag_names = [row[0] for row in result.fetchall()]
            
            # Cache results
            await self._cache_autocomplete(cache_key, tag_names)
            
            return tag_names
            
        except Exception as e:
            logger.error(f"Error in tag autocomplete: {e}")
            return []  # Return empty list on error to maintain performance
    
    async def get_search_suggestions(
        self, 
        query: str, 
        user: User,
        limit: int = 5
    ) -> List[str]:
        """
        Get search suggestions based on user query patterns and popular content.
        
        Args:
            query: Partial search query
            user: User requesting suggestions
            limit: Maximum number of suggestions
            
        Returns:
            List[str]: List of search suggestions
        """
        try:
            if not query or len(query.strip()) < 2:
                return []
            
            sanitized_query = query.strip().lower()
            
            # Check cache
            cache_key = f"suggestions:{sanitized_query}:{limit}"
            cached_suggestions = await self._get_cached_autocomplete(cache_key)
            if cached_suggestions is not None:
                return cached_suggestions
            
            # Get suggestions from document titles and content
            suggestions_query = text("""
                SELECT DISTINCT 
                    CASE 
                        WHEN d.title ILIKE :query_like THEN d.title
                        ELSE regexp_replace(
                            substring(d.content from '(?i)\\w*' || :query || '\\w*'),
                            '[^a-zA-Z0-9\\s]', '', 'g'
                        )
                    END as suggestion
                FROM documents d
                WHERE (d.title ILIKE :query_like OR d.content ILIKE :query_like)
                  AND d.status = 'published'
                  AND suggestion IS NOT NULL
                  AND length(suggestion) > 0
                ORDER BY 
                    CASE WHEN suggestion ILIKE :query_start THEN 1 ELSE 2 END,
                    length(suggestion),
                    suggestion
                LIMIT :limit
            """)
            
            result = await self.db.execute(
                suggestions_query,
                {
                    "query": sanitized_query,
                    "query_like": f"%{sanitized_query}%",
                    "query_start": f"{sanitized_query}%",
                    "limit": limit
                }
            )
            
            suggestions = [row[0].strip() for row in result.fetchall() if row[0] and row[0].strip()]
            
            # Cache suggestions
            await self._cache_autocomplete(cache_key, suggestions)
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Error getting search suggestions: {e}")
            return []
    
    async def index_document(self, document: Document) -> None:
        """
        Index a document for search (search vector is updated automatically by trigger).
        
        Args:
            document: Document to index
        """
        try:
            # The search vector is automatically updated by the database trigger
            # This method can be used for additional indexing operations if needed
            logger.debug(f"Document indexed: {document.id}")
            
        except Exception as e:
            logger.error(f"Error indexing document {document.id}: {e}")
    
    async def remove_from_index(self, doc_id: uuid.UUID) -> None:
        """
        Remove a document from search index.
        
        Args:
            doc_id: Document ID to remove
        """
        try:
            # Clear any cached search results that might contain this document
            # In a production system, you might want to implement more sophisticated cache invalidation
            logger.debug(f"Document removed from index: {doc_id}")
            
        except Exception as e:
            logger.error(f"Error removing document from index {doc_id}: {e}")
    
    # Private helper methods
    
    def _sanitize_search_query(self, query: str) -> str:
        """Sanitize and validate search query."""
        if not query:
            return ""
        
        # Remove special characters that could break PostgreSQL full-text search
        sanitized = re.sub(r'[^\w\s\-\'"&|!()]', ' ', query.strip())
        
        # Remove excessive whitespace
        sanitized = re.sub(r'\s+', ' ', sanitized).strip()
        
        # Limit query length
        if len(sanitized) > 200:
            sanitized = sanitized[:200]
        
        return sanitized
    
    def _build_search_query(self, query: str, filters: SearchFilters, user: User):
        """Build PostgreSQL full-text search query with filters and ranking."""
        # Convert query to tsquery format
        tsquery = self._build_tsquery(query)
        
        # Base query with ranking
        base_query = select(
            Document.id,
            Document.title,
            Document.slug,
            Document.folder_path,
            Document.content,
            Document.status,
            Document.updated_at,
            User.username.label('author_name'),
            func.ts_rank(Document.search_vector, func.to_tsquery('english', tsquery)).label('rank'),
            func.ts_headline(
                'english',
                Document.content,
                func.to_tsquery('english', tsquery),
                'MaxWords=50, MinWords=20, ShortWord=3, HighlightAll=false, MaxFragments=1'
            ).label('content_snippet'),
            func.ts_headline(
                'english', 
                Document.title,
                func.to_tsquery('english', tsquery),
                'HighlightAll=false'
            ).label('highlighted_title')
        ).select_from(
            Document.__table__.join(User.__table__, Document.author_id == User.id)
        ).where(
            Document.search_vector.op('@@')(func.to_tsquery('english', tsquery))
        )
        
        # Apply visibility controls
        if user.role.value != "admin":
            base_query = base_query.where(
                or_(
                    Document.status == DocumentStatus.PUBLISHED,
                    and_(
                        Document.status == DocumentStatus.DRAFT,
                        Document.author_id == user.id
                    )
                )
            )
        
        # Apply filters
        if filters.folder_path:
            base_query = base_query.where(Document.folder_path.like(f"{filters.folder_path}%"))
        
        if filters.status:
            base_query = base_query.where(Document.status == filters.status)
        
        if filters.author_id:
            base_query = base_query.where(Document.author_id == filters.author_id)
        
        if filters.tags:
            # Join with document_tags to filter by tags
            base_query = base_query.join(
                DocumentTag, Document.id == DocumentTag.document_id
            ).join(
                Tag, DocumentTag.tag_id == Tag.id
            ).where(
                Tag.name.in_(filters.tags)
            ).group_by(
                Document.id, Document.title, Document.slug, Document.folder_path,
                Document.content, Document.status, Document.updated_at, User.username,
                Document.search_vector
            ).having(
                func.count(Tag.id) == len(filters.tags)  # Must match all tags
            )
        
        # Order by relevance rank
        base_query = base_query.order_by(desc('rank'), Document.updated_at.desc())
        
        return base_query
    
    def _build_count_query(self, query: str, filters: SearchFilters, user: User):
        """Build count query for search results."""
        tsquery = self._build_tsquery(query)
        
        count_query = select(func.count(Document.id.distinct())).select_from(
            Document.__table__.join(User.__table__, Document.author_id == User.id)
        ).where(
            Document.search_vector.op('@@')(func.to_tsquery('english', tsquery))
        )
        
        # Apply same filters as main query
        if user.role.value != "admin":
            count_query = count_query.where(
                or_(
                    Document.status == DocumentStatus.PUBLISHED,
                    and_(
                        Document.status == DocumentStatus.DRAFT,
                        Document.author_id == user.id
                    )
                )
            )
        
        if filters.folder_path:
            count_query = count_query.where(Document.folder_path.like(f"{filters.folder_path}%"))
        
        if filters.status:
            count_query = count_query.where(Document.status == filters.status)
        
        if filters.author_id:
            count_query = count_query.where(Document.author_id == filters.author_id)
        
        if filters.tags:
            count_query = count_query.join(
                DocumentTag, Document.id == DocumentTag.document_id
            ).join(
                Tag, DocumentTag.tag_id == Tag.id
            ).where(
                Tag.name.in_(filters.tags)
            ).group_by(Document.id).having(
                func.count(Tag.id) == len(filters.tags)
            )
        
        return count_query
    
    def _build_tsquery(self, query: str) -> str:
        """Build PostgreSQL tsquery from search query."""
        # Split query into terms
        terms = query.split()
        
        if not terms:
            return ""
        
        # Build tsquery with AND logic for multiple terms
        tsquery_parts = []
        for term in terms:
            # Add prefix matching for partial words
            if len(term) > 2:
                tsquery_parts.append(f"{term}:*")
            else:
                tsquery_parts.append(term)
        
        return " & ".join(tsquery_parts)
    
    async def _process_search_result(self, row, query: str) -> SearchResult:
        """Process a search result row into SearchResult object."""
        # Get tags for the document
        tags_result = await self.db.execute(
            select(Tag.name)
            .join(DocumentTag, Tag.id == DocumentTag.tag_id)
            .where(DocumentTag.document_id == row.id)
        )
        tags = [tag[0] for tag in tags_result.fetchall()]
        
        return SearchResult(
            document_id=row.id,
            title=row.title,
            slug=row.slug,
            folder_path=row.folder_path,
            content_snippet=row.content_snippet or row.content[:200] + "...",
            highlighted_title=row.highlighted_title or row.title,
            highlighted_snippet=row.content_snippet or row.content[:200] + "...",
            rank=float(row.rank),
            tags=tags,
            author_name=row.author_name,
            updated_at=row.updated_at.isoformat(),
            status=row.status.value
        )
    
    def _generate_cache_key(
        self, 
        query: str, 
        filters: SearchFilters, 
        user_id: uuid.UUID,
        limit: int, 
        offset: int
    ) -> str:
        """Generate cache key for search results."""
        filter_str = f"{filters.folder_path}:{filters.status}:{filters.author_id}:{filters.tags}"
        return f"search:{hash(query)}:{hash(filter_str)}:{user_id}:{limit}:{offset}"
    
    async def _get_cached_search_result(self, cache_key: str) -> Optional[SearchResults]:
        """Get cached search results."""
        try:
            if not self.redis:
                return None
            
            cached_data = await self.redis.get(cache_key)
            if cached_data:
                # In a production system, you would deserialize the cached data
                # For now, we'll skip caching to keep the implementation simple
                pass
            
        except Exception as e:
            logger.warning(f"Error getting cached search result: {e}")
        
        return None
    
    async def _cache_search_result(self, cache_key: str, results: SearchResults) -> None:
        """Cache search results."""
        try:
            if not self.redis:
                return
            
            # In a production system, you would serialize and cache the results
            # For now, we'll skip caching to keep the implementation simple
            pass
            
        except Exception as e:
            logger.warning(f"Error caching search result: {e}")
    
    async def _get_cached_autocomplete(self, cache_key: str) -> Optional[List[str]]:
        """Get cached autocomplete results."""
        try:
            if not self.redis:
                return None
            
            cached_data = await self.redis.get(cache_key)
            if cached_data:
                import json
                return json.loads(cached_data)
            
        except Exception as e:
            logger.warning(f"Error getting cached autocomplete: {e}")
        
        return None
    
    async def _cache_autocomplete(self, cache_key: str, results: List[str]) -> None:
        """Cache autocomplete results."""
        try:
            if not self.redis:
                return
            
            import json
            await self.redis.setex(
                cache_key, 
                self.autocomplete_cache_ttl, 
                json.dumps(results)
            )
            
        except Exception as e:
            logger.warning(f"Error caching autocomplete: {e}")
    as
ync def record_search_analytics(
        self, 
        query: str, 
        user: User, 
        results_count: int,
        execution_time_ms: float,
        filters: SearchFilters
    ) -> None:
        """
        Record search analytics for performance monitoring and query pattern analysis.
        
        Args:
            query: Search query
            user: User who performed the search
            results_count: Number of results returned
            execution_time_ms: Search execution time
            filters: Applied search filters
        """
        try:
            if not self.redis:
                return
            
            # Create analytics record
            analytics_data = {
                "query": query,
                "user_id": str(user.id),
                "username": user.username,
                "results_count": results_count,
                "execution_time_ms": execution_time_ms,
                "filters": {
                    "folder_path": filters.folder_path,
                    "tags": filters.tags,
                    "status": filters.status.value if filters.status else None,
                    "author_id": str(filters.author_id) if filters.author_id else None
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Store in Redis with expiration (keep for 30 days)
            analytics_key = f"search_analytics:{datetime.utcnow().strftime('%Y-%m-%d')}:{uuid.uuid4().hex[:8]}"
            import json
            await self.redis.setex(
                analytics_key,
                30 * 24 * 3600,  # 30 days
                json.dumps(analytics_data)
            )
            
            # Update search performance metrics
            await self._update_performance_metrics(execution_time_ms)
            
            # Track popular queries
            await self._track_popular_query(query)
            
        except Exception as e:
            logger.warning(f"Error recording search analytics: {e}")
    
    async def _update_performance_metrics(self, execution_time_ms: float) -> None:
        """Update search performance metrics in Redis."""
        try:
            if not self.redis:
                return
            
            # Update daily performance metrics
            today = datetime.utcnow().strftime('%Y-%m-%d')
            metrics_key = f"search_metrics:{today}"
            
            # Use Redis pipeline for atomic updates
            pipe = self.redis.pipeline()
            pipe.hincrby(metrics_key, "total_searches", 1)
            pipe.hincrbyfloat(metrics_key, "total_time_ms", execution_time_ms)
            pipe.expire(metrics_key, 7 * 24 * 3600)  # Keep for 7 days
            
            # Track slow searches (> 1000ms)
            if execution_time_ms > 1000:
                pipe.hincrby(metrics_key, "slow_searches", 1)
            
            # Track fast searches (< 100ms for autocomplete requirement)
            if execution_time_ms < 100:
                pipe.hincrby(metrics_key, "fast_searches", 1)
            
            await pipe.execute()
            
        except Exception as e:
            logger.warning(f"Error updating performance metrics: {e}")
    
    async def _track_popular_query(self, query: str) -> None:
        """Track popular search queries."""
        try:
            if not self.redis:
                return
            
            # Normalize query for tracking
            normalized_query = query.lower().strip()
            if len(normalized_query) < 2:
                return
            
            # Track in daily popular queries
            today = datetime.utcnow().strftime('%Y-%m-%d')
            popular_key = f"popular_queries:{today}"
            
            await self.redis.zincrby(popular_key, 1, normalized_query)
            await self.redis.expire(popular_key, 7 * 24 * 3600)  # Keep for 7 days
            
        except Exception as e:
            logger.warning(f"Error tracking popular query: {e}")
    
    async def get_search_performance_metrics(self, days: int = 7) -> Dict[str, Any]:
        """
        Get search performance metrics for monitoring and optimization.
        
        Args:
            days: Number of days to retrieve metrics for
            
        Returns:
            Dict containing performance metrics
        """
        try:
            if not self.redis:
                return {}
            
            metrics = {
                "daily_metrics": [],
                "summary": {
                    "total_searches": 0,
                    "average_time_ms": 0.0,
                    "slow_searches": 0,
                    "fast_searches": 0,
                    "performance_score": 0.0
                }
            }
            
            total_searches = 0
            total_time = 0.0
            total_slow = 0
            total_fast = 0
            
            # Get metrics for each day
            for i in range(days):
                date = (datetime.utcnow() - timedelta(days=i)).strftime('%Y-%m-%d')
                metrics_key = f"search_metrics:{date}"
                
                daily_data = await self.redis.hgetall(metrics_key)
                if daily_data:
                    searches = int(daily_data.get(b"total_searches", 0))
                    time_ms = float(daily_data.get(b"total_time_ms", 0))
                    slow = int(daily_data.get(b"slow_searches", 0))
                    fast = int(daily_data.get(b"fast_searches", 0))
                    
                    daily_metrics = {
                        "date": date,
                        "total_searches": searches,
                        "average_time_ms": time_ms / searches if searches > 0 else 0.0,
                        "slow_searches": slow,
                        "fast_searches": fast,
                        "performance_score": (fast / searches * 100) if searches > 0 else 0.0
                    }
                    
                    metrics["daily_metrics"].append(daily_metrics)
                    
                    total_searches += searches
                    total_time += time_ms
                    total_slow += slow
                    total_fast += fast
            
            # Calculate summary
            if total_searches > 0:
                metrics["summary"] = {
                    "total_searches": total_searches,
                    "average_time_ms": total_time / total_searches,
                    "slow_searches": total_slow,
                    "fast_searches": total_fast,
                    "performance_score": (total_fast / total_searches * 100)
                }
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error getting search performance metrics: {e}")
            return {}
    
    async def get_popular_queries(self, days: int = 7, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get popular search queries for analysis and optimization.
        
        Args:
            days: Number of days to analyze
            limit: Maximum number of queries to return
            
        Returns:
            List of popular queries with counts
        """
        try:
            if not self.redis:
                return []
            
            # Aggregate popular queries across days
            all_queries = {}
            
            for i in range(days):
                date = (datetime.utcnow() - timedelta(days=i)).strftime('%Y-%m-%d')
                popular_key = f"popular_queries:{date}"
                
                daily_queries = await self.redis.zrevrange(popular_key, 0, -1, withscores=True)
                for query_bytes, count in daily_queries:
                    query = query_bytes.decode('utf-8')
                    all_queries[query] = all_queries.get(query, 0) + int(count)
            
            # Sort by popularity and return top queries
            popular_queries = [
                {"query": query, "count": count}
                for query, count in sorted(all_queries.items(), key=lambda x: x[1], reverse=True)[:limit]
            ]
            
            return popular_queries
            
        except Exception as e:
            logger.error(f"Error getting popular queries: {e}")
            return []