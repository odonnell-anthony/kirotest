"""
Performance tests for search functionality.
"""
import pytest
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from httpx import AsyncClient

from tests.conftest import UserFactory, DocumentFactory, TagFactory


@pytest.mark.performance
class TestSearchPerformance:
    """Test search performance requirements."""
    
    @pytest.mark.asyncio
    async def test_autocomplete_response_time(self, test_client: AsyncClient, test_db, performance_timer):
        """Test that autocomplete responds within 100ms requirement."""
        # Create test tags for autocomplete
        tag_names = [
            "python", "pytorch", "programming", "performance", "production",
            "javascript", "java", "json", "jwt", "jenkins",
            "docker", "database", "django", "development", "deployment"
        ]
        
        for name in tag_names:
            await TagFactory.create_and_save_tag(test_db, name=name, usage_count=10)
        
        # Test autocomplete performance
        query = "py"
        
        performance_timer.start()
        response = await test_client.get(f"/api/v1/search/autocomplete?q={query}")
        performance_timer.stop()
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response time is under 100ms
        assert performance_timer.elapsed_ms < 100, f"Autocomplete took {performance_timer.elapsed_ms}ms, should be < 100ms"
        
        # Verify results are relevant
        suggestions = data["suggestions"]
        assert len(suggestions) > 0
        assert all("py" in suggestion["name"].lower() for suggestion in suggestions)
    
    @pytest.mark.asyncio
    async def test_search_performance_with_large_dataset(self, test_client: AsyncClient, test_db, performance_timer):
        """Test search performance with large dataset."""
        # Create large dataset
        user = await UserFactory.create_and_save_user(test_db)
        
        # Create 1000 documents
        documents = []
        for i in range(1000):
            doc = await DocumentFactory.create_and_save_document(
                test_db,
                title=f"Document {i}",
                content=f"This is document number {i} with content about programming and development.",
                author_id=user.id
            )
            documents.append(doc)
        
        # Test search performance
        query = "programming"
        
        performance_timer.start()
        response = await test_client.get(f"/api/v1/search?q={query}")
        performance_timer.stop()
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response time is reasonable (under 500ms for large dataset)
        assert performance_timer.elapsed_ms < 500, f"Search took {performance_timer.elapsed_ms}ms, should be < 500ms"
        
        # Verify results are returned
        assert data["total"] > 0
        assert len(data["results"]) > 0
    
    @pytest.mark.asyncio
    async def test_concurrent_autocomplete_requests(self, test_client: AsyncClient, test_db):
        """Test autocomplete performance under concurrent load."""
        # Create test tags
        for i in range(50):
            await TagFactory.create_and_save_tag(test_db, name=f"tag-{i:03d}", usage_count=i)
        
        async def make_autocomplete_request(query_suffix):
            """Make a single autocomplete request."""
            start_time = time.perf_counter()
            response = await test_client.get(f"/api/v1/search/autocomplete?q=tag-{query_suffix}")
            end_time = time.perf_counter()
            
            return {
                "status_code": response.status_code,
                "response_time_ms": (end_time - start_time) * 1000,
                "query": f"tag-{query_suffix}"
            }
        
        # Make 20 concurrent requests
        tasks = []
        for i in range(20):
            query_suffix = f"{i:02d}"
            tasks.append(make_autocomplete_request(query_suffix))
        
        # Execute concurrent requests
        start_time = time.perf_counter()
        results = await asyncio.gather(*tasks)
        end_time = time.perf_counter()
        
        total_time_ms = (end_time - start_time) * 1000
        
        # Verify all requests succeeded
        assert all(result["status_code"] == 200 for result in results)
        
        # Verify individual response times are under 100ms
        slow_requests = [r for r in results if r["response_time_ms"] > 100]
        assert len(slow_requests) == 0, f"Slow requests: {slow_requests}"
        
        # Verify total time for concurrent requests is reasonable
        assert total_time_ms < 2000, f"Concurrent requests took {total_time_ms}ms, should be < 2000ms"
        
        # Calculate average response time
        avg_response_time = sum(r["response_time_ms"] for r in results) / len(results)
        assert avg_response_time < 50, f"Average response time {avg_response_time}ms should be < 50ms"
    
    @pytest.mark.asyncio
    async def test_search_pagination_performance(self, test_client: AsyncClient, test_db, performance_timer):
        """Test search pagination performance."""
        # Create test data
        user = await UserFactory.create_and_save_user(test_db)
        
        # Create 500 documents with searchable content
        for i in range(500):
            await DocumentFactory.create_and_save_document(
                test_db,
                title=f"Test Document {i}",
                content=f"This is test document {i} with searchable content about testing and development.",
                author_id=user.id
            )
        
        # Test different page sizes and offsets
        test_cases = [
            {"page": 1, "size": 10},
            {"page": 1, "size": 50},
            {"page": 5, "size": 20},
            {"page": 10, "size": 10},
        ]
        
        for case in test_cases:
            performance_timer.start()
            response = await test_client.get(
                f"/api/v1/search?q=test&page={case['page']}&size={case['size']}"
            )
            performance_timer.stop()
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify response time is reasonable
            assert performance_timer.elapsed_ms < 300, f"Pagination search took {performance_timer.elapsed_ms}ms"
            
            # Verify pagination data
            assert data["page"] == case["page"]
            assert data["size"] == case["size"]
            assert len(data["results"]) <= case["size"]
    
    @pytest.mark.asyncio
    async def test_tag_autocomplete_memory_usage(self, test_client: AsyncClient, test_db):
        """Test that tag autocomplete doesn't cause memory leaks."""
        import psutil
        import os
        
        # Get initial memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        # Create test tags
        for i in range(100):
            await TagFactory.create_and_save_tag(test_db, name=f"memory-test-tag-{i:03d}", usage_count=i)
        
        # Make many autocomplete requests
        for i in range(100):
            query = f"memory-test-tag-{i % 10:02d}"
            response = await test_client.get(f"/api/v1/search/autocomplete?q={query}")
            assert response.status_code == 200
        
        # Check memory usage after requests
        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory
        
        # Memory increase should be reasonable (less than 50MB)
        max_memory_increase = 50 * 1024 * 1024  # 50MB in bytes
        assert memory_increase < max_memory_increase, f"Memory increased by {memory_increase / 1024 / 1024:.2f}MB"


@pytest.mark.performance
class TestDatabasePerformance:
    """Test database operation performance."""
    
    @pytest.mark.asyncio
    async def test_document_creation_performance(self, test_db, performance_timer):
        """Test document creation performance."""
        user = await UserFactory.create_and_save_user(test_db)
        
        # Test creating multiple documents
        performance_timer.start()
        
        for i in range(100):
            document = DocumentFactory.create_document(
                title=f"Performance Test Document {i}",
                content=f"Content for document {i}",
                author_id=user.id
            )
            test_db.add(document)
        
        await test_db.commit()
        performance_timer.stop()
        
        # Should create 100 documents in reasonable time
        assert performance_timer.elapsed_ms < 5000, f"Creating 100 documents took {performance_timer.elapsed_ms}ms"
        
        # Calculate average time per document
        avg_time_per_doc = performance_timer.elapsed_ms / 100
        assert avg_time_per_doc < 50, f"Average time per document: {avg_time_per_doc}ms"
    
    @pytest.mark.asyncio
    async def test_complex_query_performance(self, test_db, performance_timer):
        """Test complex database query performance."""
        from sqlalchemy import select, and_, or_
        from sqlalchemy.orm import selectinload
        
        # Create test data
        user = await UserFactory.create_and_save_user(test_db)
        
        # Create documents with tags
        for i in range(200):
            document = await DocumentFactory.create_and_save_document(
                test_db,
                title=f"Complex Query Test {i}",
                folder_path=f"/folder-{i % 10}/",
                author_id=user.id
            )
            
            # Add tags to some documents
            if i % 3 == 0:
                tag = await TagFactory.create_and_save_tag(test_db, name=f"tag-{i % 5}")
                # Associate tag with document (simplified)
        
        # Test complex query with joins and filters
        performance_timer.start()
        
        stmt = select(Document).where(
            and_(
                Document.author_id == user.id,
                or_(
                    Document.folder_path.like("/folder-1/%"),
                    Document.folder_path.like("/folder-2/%")
                )
            )
        ).options(selectinload(Document.tags)).limit(50)
        
        result = await test_db.execute(stmt)
        documents = result.scalars().all()
        
        performance_timer.stop()
        
        # Complex query should complete quickly
        assert performance_timer.elapsed_ms < 1000, f"Complex query took {performance_timer.elapsed_ms}ms"
        assert len(documents) > 0
    
    @pytest.mark.asyncio
    async def test_full_text_search_performance(self, test_db, performance_timer):
        """Test full-text search performance."""
        from sqlalchemy import select, func
        
        # Create documents with searchable content
        user = await UserFactory.create_and_save_user(test_db)
        
        search_terms = ["python", "javascript", "database", "programming", "development"]
        
        for i in range(500):
            term = search_terms[i % len(search_terms)]
            content = f"This document is about {term} programming and software development. " * 10
            
            await DocumentFactory.create_and_save_document(
                test_db,
                title=f"Search Test Document {i}",
                content=content,
                author_id=user.id
            )
        
        # Test full-text search performance
        search_term = "python"
        
        performance_timer.start()
        
        # Simulate full-text search (simplified)
        stmt = select(Document).where(
            Document.content.contains(search_term)
        ).limit(20)
        
        result = await test_db.execute(stmt)
        documents = result.scalars().all()
        
        performance_timer.stop()
        
        # Full-text search should be fast
        assert performance_timer.elapsed_ms < 500, f"Full-text search took {performance_timer.elapsed_ms}ms"
        assert len(documents) > 0


@pytest.mark.performance
class TestConcurrencyPerformance:
    """Test performance under concurrent load."""
    
    @pytest.mark.asyncio
    async def test_concurrent_document_creation(self, test_client: AsyncClient, test_db):
        """Test concurrent document creation performance."""
        async def create_document(doc_index):
            """Create a single document."""
            doc_data = {
                "title": f"Concurrent Document {doc_index}",
                "content": f"Content for concurrent document {doc_index}",
                "folder_path": "/concurrent/",
                "status": "published"
            }
            
            start_time = time.perf_counter()
            response = await test_client.post("/api/v1/documents", json=doc_data)
            end_time = time.perf_counter()
            
            return {
                "status_code": response.status_code,
                "response_time_ms": (end_time - start_time) * 1000,
                "doc_index": doc_index
            }
        
        # Create 10 documents concurrently
        tasks = [create_document(i) for i in range(10)]
        
        start_time = time.perf_counter()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = time.perf_counter()
        
        total_time_ms = (end_time - start_time) * 1000
        
        # Filter out exceptions
        successful_results = [r for r in results if not isinstance(r, Exception)]
        
        # Verify most requests succeeded
        assert len(successful_results) >= 8, f"Only {len(successful_results)} out of 10 requests succeeded"
        
        # Verify individual response times are reasonable
        slow_requests = [r for r in successful_results if r["response_time_ms"] > 2000]
        assert len(slow_requests) <= 2, f"Too many slow requests: {len(slow_requests)}"
        
        # Verify total time is reasonable
        assert total_time_ms < 5000, f"Concurrent document creation took {total_time_ms}ms"
    
    @pytest.mark.asyncio
    async def test_concurrent_search_requests(self, test_client: AsyncClient, test_db):
        """Test concurrent search request performance."""
        # Create searchable documents
        user = await UserFactory.create_and_save_user(test_db)
        
        for i in range(100):
            await DocumentFactory.create_and_save_document(
                test_db,
                title=f"Searchable Document {i}",
                content=f"This document contains searchable content about topic {i % 10}",
                author_id=user.id
            )
        
        async def search_request(query_index):
            """Make a single search request."""
            query = f"topic {query_index % 10}"
            
            start_time = time.perf_counter()
            response = await test_client.get(f"/api/v1/search?q={query}")
            end_time = time.perf_counter()
            
            return {
                "status_code": response.status_code,
                "response_time_ms": (end_time - start_time) * 1000,
                "query": query
            }
        
        # Make 15 concurrent search requests
        tasks = [search_request(i) for i in range(15)]
        
        start_time = time.perf_counter()
        results = await asyncio.gather(*tasks)
        end_time = time.perf_counter()
        
        total_time_ms = (end_time - start_time) * 1000
        
        # Verify all requests succeeded
        assert all(result["status_code"] == 200 for result in results)
        
        # Verify individual response times
        slow_requests = [r for r in results if r["response_time_ms"] > 1000]
        assert len(slow_requests) <= 3, f"Too many slow search requests: {len(slow_requests)}"
        
        # Verify total time for concurrent searches
        assert total_time_ms < 3000, f"Concurrent searches took {total_time_ms}ms"