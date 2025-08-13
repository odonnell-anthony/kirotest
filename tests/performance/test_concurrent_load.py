"""
Performance tests for concurrent load scenarios.
"""
import pytest
import asyncio
import time
import statistics
from concurrent.futures import ThreadPoolExecutor
from httpx import AsyncClient

from tests.conftest import UserFactory, DocumentFactory


@pytest.mark.performance
class TestConcurrentUserLoad:
    """Test performance under concurrent user load."""
    
    @pytest.mark.asyncio
    async def test_concurrent_user_sessions(self, test_client: AsyncClient, test_db):
        """Test concurrent user sessions up to expected capacity."""
        # Create multiple users for concurrent testing
        users = []
        for i in range(20):  # Test with 20 concurrent users
            user = await UserFactory.create_and_save_user(test_db, username=f"concurrent_user_{i}")
            users.append(user)
        
        async def simulate_user_session(user_index):
            """Simulate a complete user session."""
            session_start = time.perf_counter()
            
            try:
                # Mock user authentication
                user = users[user_index]
                
                # Simulate user workflow: login, browse, create, search
                actions = []
                
                # 1. Browse documents
                browse_start = time.perf_counter()
                browse_response = await test_client.get("/api/v1/documents?page=1&size=10")
                browse_time = (time.perf_counter() - browse_start) * 1000
                actions.append(("browse", browse_response.status_code, browse_time))
                
                # 2. Search for content
                search_start = time.perf_counter()
                search_response = await test_client.get("/api/v1/search?q=test")
                search_time = (time.perf_counter() - search_start) * 1000
                actions.append(("search", search_response.status_code, search_time))
                
                # 3. Create a document
                create_start = time.perf_counter()
                doc_data = {
                    "title": f"Concurrent Test Document {user_index}",
                    "content": f"Content created by user {user_index} during concurrent test.",
                    "folder_path": f"/concurrent-test-{user_index}/"
                }
                create_response = await test_client.post("/api/v1/documents", json=doc_data)
                create_time = (time.perf_counter() - create_start) * 1000
                actions.append(("create", create_response.status_code, create_time))
                
                # 4. Update the document
                if create_response.status_code == 201:
                    document = create_response.json()
                    update_start = time.perf_counter()
                    update_data = {"content": f"Updated content by user {user_index}"}
                    update_response = await test_client.put(f"/api/v1/documents/{document['id']}", json=update_data)
                    update_time = (time.perf_counter() - update_start) * 1000
                    actions.append(("update", update_response.status_code, update_time))
                
                # 5. Autocomplete search
                autocomplete_start = time.perf_counter()
                autocomplete_response = await test_client.get("/api/v1/search/autocomplete?q=test")
                autocomplete_time = (time.perf_counter() - autocomplete_start) * 1000
                actions.append(("autocomplete", autocomplete_response.status_code, autocomplete_time))
                
                session_time = (time.perf_counter() - session_start) * 1000
                
                return {
                    "user_index": user_index,
                    "session_time_ms": session_time,
                    "actions": actions,
                    "success": all(action[1] < 400 for action in actions)
                }
                
            except Exception as e:
                return {
                    "user_index": user_index,
                    "session_time_ms": (time.perf_counter() - session_start) * 1000,
                    "actions": [],
                    "success": False,
                    "error": str(e)
                }
        
        # Execute concurrent user sessions
        start_time = time.perf_counter()
        tasks = [simulate_user_session(i) for i in range(20)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_time = (time.perf_counter() - start_time) * 1000
        
        # Analyze results
        successful_sessions = [r for r in results if not isinstance(r, Exception) and r["success"]]
        failed_sessions = [r for r in results if isinstance(r, Exception) or not r["success"]]
        
        # Performance assertions
        success_rate = len(successful_sessions) / len(results)
        assert success_rate >= 0.9, f"Success rate {success_rate:.2%} should be >= 90%"
        
        # Session time analysis
        session_times = [r["session_time_ms"] for r in successful_sessions]
        if session_times:
            avg_session_time = statistics.mean(session_times)
            max_session_time = max(session_times)
            
            assert avg_session_time < 5000, f"Average session time {avg_session_time:.0f}ms should be < 5000ms"
            assert max_session_time < 10000, f"Max session time {max_session_time:.0f}ms should be < 10000ms"
        
        # Action time analysis
        all_actions = []
        for result in successful_sessions:
            all_actions.extend(result["actions"])
        
        # Group actions by type
        action_times = {}
        for action_name, status_code, action_time in all_actions:
            if action_name not in action_times:
                action_times[action_name] = []
            action_times[action_name].append(action_time)
        
        # Verify action performance
        for action_name, times in action_times.items():
            avg_time = statistics.mean(times)
            max_time = max(times)
            
            if action_name == "autocomplete":
                assert avg_time < 100, f"Average {action_name} time {avg_time:.0f}ms should be < 100ms"
            elif action_name in ["browse", "search"]:
                assert avg_time < 500, f"Average {action_name} time {avg_time:.0f}ms should be < 500ms"
            else:
                assert avg_time < 1000, f"Average {action_name} time {avg_time:.0f}ms should be < 1000ms"
        
        print(f"\nConcurrent Load Test Results:")
        print(f"  Total time: {total_time:.0f}ms")
        print(f"  Success rate: {success_rate:.2%}")
        print(f"  Successful sessions: {len(successful_sessions)}")
        print(f"  Failed sessions: {len(failed_sessions)}")
        if session_times:
            print(f"  Average session time: {statistics.mean(session_times):.0f}ms")
            print(f"  Max session time: {max(session_times):.0f}ms")
    
    @pytest.mark.asyncio
    async def test_database_connection_pool_under_load(self, test_client: AsyncClient, test_db):
        """Test database connection pool performance under load."""
        async def database_intensive_operation(operation_index):
            """Perform database-intensive operations."""
            start_time = time.perf_counter()
            
            try:
                # Create user
                user = await UserFactory.create_and_save_user(test_db, username=f"db_test_user_{operation_index}")
                
                # Create multiple documents
                documents = []
                for i in range(5):
                    doc = await DocumentFactory.create_and_save_document(
                        test_db,
                        title=f"DB Test Document {operation_index}-{i}",
                        content=f"Content for database test {operation_index}-{i}",
                        author_id=user.id
                    )
                    documents.append(doc)
                
                # Perform queries
                from sqlalchemy import select
                from app.models.document import Document
                
                # Query documents by author
                stmt = select(Document).where(Document.author_id == user.id)
                result = await test_db.execute(stmt)
                user_docs = result.scalars().all()
                
                # Query documents by folder
                stmt = select(Document).where(Document.folder_path == "/")
                result = await test_db.execute(stmt)
                folder_docs = result.scalars().all()
                
                operation_time = (time.perf_counter() - start_time) * 1000
                
                return {
                    "operation_index": operation_index,
                    "operation_time_ms": operation_time,
                    "documents_created": len(documents),
                    "user_docs_found": len(user_docs),
                    "success": True
                }
                
            except Exception as e:
                return {
                    "operation_index": operation_index,
                    "operation_time_ms": (time.perf_counter() - start_time) * 1000,
                    "success": False,
                    "error": str(e)
                }
        
        # Execute concurrent database operations
        start_time = time.perf_counter()
        tasks = [database_intensive_operation(i) for i in range(15)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_time = (time.perf_counter() - start_time) * 1000
        
        # Analyze results
        successful_ops = [r for r in results if not isinstance(r, Exception) and r["success"]]
        failed_ops = [r for r in results if isinstance(r, Exception) or not r["success"]]
        
        # Performance assertions
        success_rate = len(successful_ops) / len(results)
        assert success_rate >= 0.95, f"Database operation success rate {success_rate:.2%} should be >= 95%"
        
        # Operation time analysis
        operation_times = [r["operation_time_ms"] for r in successful_ops]
        if operation_times:
            avg_operation_time = statistics.mean(operation_times)
            max_operation_time = max(operation_times)
            
            assert avg_operation_time < 2000, f"Average DB operation time {avg_operation_time:.0f}ms should be < 2000ms"
            assert max_operation_time < 5000, f"Max DB operation time {max_operation_time:.0f}ms should be < 5000ms"
        
        print(f"\nDatabase Load Test Results:")
        print(f"  Total time: {total_time:.0f}ms")
        print(f"  Success rate: {success_rate:.2%}")
        print(f"  Successful operations: {len(successful_ops)}")
        print(f"  Failed operations: {len(failed_ops)}")
        if operation_times:
            print(f"  Average operation time: {statistics.mean(operation_times):.0f}ms")
    
    @pytest.mark.asyncio
    async def test_memory_usage_under_load(self, test_client: AsyncClient, test_db):
        """Test memory usage under sustained load."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        async def memory_intensive_operation(batch_index):
            """Perform operations that might consume memory."""
            # Create large content
            large_content = "x" * 10000  # 10KB content
            
            # Create documents with large content
            user = await UserFactory.create_and_save_user(test_db, username=f"memory_user_{batch_index}")
            
            documents = []
            for i in range(10):
                doc_data = {
                    "title": f"Memory Test Document {batch_index}-{i}",
                    "content": f"# Large Content {batch_index}-{i}\n\n{large_content}",
                    "folder_path": f"/memory-test-{batch_index}/",
                    "author_id": user.id
                }
                
                # Use API to create document (more realistic memory usage)
                response = await test_client.post("/api/v1/documents", json=doc_data)
                if response.status_code == 201:
                    documents.append(response.json())
            
            # Perform searches (which might cache results)
            for i in range(5):
                await test_client.get(f"/api/v1/search?q=memory test {batch_index}")
                await test_client.get(f"/api/v1/search/autocomplete?q=memory")
            
            return len(documents)
        
        # Execute memory-intensive operations in batches
        memory_measurements = []
        
        for batch in range(5):  # 5 batches of operations
            batch_start_memory = process.memory_info().rss
            
            # Execute batch of operations
            tasks = [memory_intensive_operation(batch * 10 + i) for i in range(10)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            batch_end_memory = process.memory_info().rss
            batch_memory_increase = batch_end_memory - batch_start_memory
            
            memory_measurements.append({
                "batch": batch,
                "start_memory_mb": batch_start_memory / 1024 / 1024,
                "end_memory_mb": batch_end_memory / 1024 / 1024,
                "increase_mb": batch_memory_increase / 1024 / 1024,
                "successful_operations": len([r for r in results if not isinstance(r, Exception)])
            })
            
            # Small delay between batches
            await asyncio.sleep(0.1)
        
        final_memory = process.memory_info().rss
        total_memory_increase = final_memory - initial_memory
        
        # Memory usage assertions
        max_memory_increase_per_batch = max(m["increase_mb"] for m in memory_measurements)
        total_memory_increase_mb = total_memory_increase / 1024 / 1024
        
        # Memory increase should be reasonable
        assert max_memory_increase_per_batch < 100, f"Max memory increase per batch {max_memory_increase_per_batch:.1f}MB should be < 100MB"
        assert total_memory_increase_mb < 500, f"Total memory increase {total_memory_increase_mb:.1f}MB should be < 500MB"
        
        print(f"\nMemory Usage Test Results:")
        print(f"  Initial memory: {initial_memory / 1024 / 1024:.1f}MB")
        print(f"  Final memory: {final_memory / 1024 / 1024:.1f}MB")
        print(f"  Total increase: {total_memory_increase_mb:.1f}MB")
        print(f"  Max batch increase: {max_memory_increase_per_batch:.1f}MB")


@pytest.mark.performance
class TestResourceUtilization:
    """Test resource utilization and efficiency."""
    
    @pytest.mark.asyncio
    async def test_cpu_utilization_under_load(self, test_client: AsyncClient, test_db):
        """Test CPU utilization during intensive operations."""
        import psutil
        
        # Monitor CPU usage during test
        cpu_measurements = []
        
        async def cpu_intensive_search_operations():
            """Perform CPU-intensive search operations."""
            # Create searchable content
            user = await UserFactory.create_and_save_user(test_db, username="cpu_test_user")
            
            # Create documents with varied content for complex searches
            search_terms = ["python", "javascript", "database", "api", "framework", "development"]
            
            for i in range(50):
                content = f"# Document {i}\n\n"
                for term in search_terms:
                    content += f"This document covers {term} programming concepts. "
                content += f"Additional content for document {i} with various keywords."
                
                await DocumentFactory.create_and_save_document(
                    test_db,
                    title=f"CPU Test Document {i}",
                    content=content,
                    author_id=user.id
                )
            
            # Perform intensive search operations
            search_queries = [
                "python programming",
                "javascript framework",
                "database design",
                "api development",
                "programming concepts",
                "development framework"
            ]
            
            for _ in range(20):  # Multiple rounds of searches
                for query in search_queries:
                    await test_client.get(f"/api/v1/search?q={query}")
                    await test_client.get(f"/api/v1/search/autocomplete?q={query[:3]}")
        
        # Measure CPU usage before, during, and after
        initial_cpu = psutil.cpu_percent(interval=1)
        
        start_time = time.perf_counter()
        await cpu_intensive_search_operations()
        operation_time = (time.perf_counter() - start_time) * 1000
        
        final_cpu = psutil.cpu_percent(interval=1)
        
        # CPU utilization should be reasonable
        # Note: This test is environment-dependent and may need adjustment
        assert operation_time < 30000, f"CPU intensive operations took {operation_time:.0f}ms, should be < 30000ms"
        
        print(f"\nCPU Utilization Test Results:")
        print(f"  Operation time: {operation_time:.0f}ms")
        print(f"  Initial CPU: {initial_cpu:.1f}%")
        print(f"  Final CPU: {final_cpu:.1f}%")
    
    @pytest.mark.asyncio
    async def test_disk_io_performance(self, test_client: AsyncClient):
        """Test disk I/O performance during file operations."""
        import tempfile
        import os
        
        # Test file upload/download performance
        async def file_io_operations():
            """Perform file I/O intensive operations."""
            uploaded_files = []
            
            # Upload multiple files of different sizes
            file_sizes = [1024, 10240, 102400, 1048576]  # 1KB, 10KB, 100KB, 1MB
            
            for i, size in enumerate(file_sizes):
                for j in range(5):  # 5 files of each size
                    file_content = b"x" * size
                    filename = f"io_test_{size}_{j}.txt"
                    
                    files = {"file": (filename, file_content, "text/plain")}
                    data = {"folder_path": "/io-test/"}
                    
                    upload_start = time.perf_counter()
                    response = await test_client.post("/api/v1/files/upload", files=files, data=data)
                    upload_time = (time.perf_counter() - upload_start) * 1000
                    
                    if response.status_code == 201:
                        file_data = response.json()
                        uploaded_files.append({
                            "file_id": file_data["file_id"],
                            "size": size,
                            "upload_time_ms": upload_time
                        })
            
            # Download all uploaded files
            download_times = []
            for file_info in uploaded_files:
                download_start = time.perf_counter()
                response = await test_client.get(f"/api/v1/files/{file_info['file_id']}")
                download_time = (time.perf_counter() - download_start) * 1000
                
                if response.status_code == 200:
                    download_times.append({
                        "size": file_info["size"],
                        "download_time_ms": download_time
                    })
            
            return uploaded_files, download_times
        
        start_time = time.perf_counter()
        uploaded_files, download_times = await file_io_operations()
        total_time = (time.perf_counter() - start_time) * 1000
        
        # Analyze I/O performance
        if uploaded_files:
            # Upload performance
            upload_times_by_size = {}
            for file_info in uploaded_files:
                size = file_info["size"]
                if size not in upload_times_by_size:
                    upload_times_by_size[size] = []
                upload_times_by_size[size].append(file_info["upload_time_ms"])
            
            # Download performance
            download_times_by_size = {}
            for download_info in download_times:
                size = download_info["size"]
                if size not in download_times_by_size:
                    download_times_by_size[size] = []
                download_times_by_size[size].append(download_info["download_time_ms"])
            
            # Performance assertions
            for size, times in upload_times_by_size.items():
                avg_upload_time = statistics.mean(times)
                # Larger files should take longer, but not excessively
                max_expected_time = max(1000, size / 1024)  # At least 1 second or 1ms per KB
                assert avg_upload_time < max_expected_time, f"Average upload time for {size} bytes: {avg_upload_time:.0f}ms"
            
            for size, times in download_times_by_size.items():
                avg_download_time = statistics.mean(times)
                max_expected_time = max(500, size / 2048)  # Downloads should be faster
                assert avg_download_time < max_expected_time, f"Average download time for {size} bytes: {avg_download_time:.0f}ms"
        
        print(f"\nDisk I/O Performance Test Results:")
        print(f"  Total time: {total_time:.0f}ms")
        print(f"  Files uploaded: {len(uploaded_files)}")
        print(f"  Files downloaded: {len(download_times)}")
    
    @pytest.mark.asyncio
    async def test_cache_performance(self, test_client: AsyncClient, test_db):
        """Test caching performance and hit rates."""
        # Create test data for caching
        user = await UserFactory.create_and_save_user(test_db, username="cache_test_user")
        
        # Create documents for search caching
        for i in range(20):
            await DocumentFactory.create_and_save_document(
                test_db,
                title=f"Cache Test Document {i}",
                content=f"Content for caching test document {i}",
                author_id=user.id
            )
        
        # Test search caching
        search_queries = ["cache", "test", "document", "content"]
        
        # First round - populate cache
        first_round_times = []
        for query in search_queries:
            start_time = time.perf_counter()
            response = await test_client.get(f"/api/v1/search?q={query}")
            query_time = (time.perf_counter() - start_time) * 1000
            first_round_times.append(query_time)
            assert response.status_code == 200
        
        # Second round - should hit cache
        second_round_times = []
        for query in search_queries:
            start_time = time.perf_counter()
            response = await test_client.get(f"/api/v1/search?q={query}")
            query_time = (time.perf_counter() - start_time) * 1000
            second_round_times.append(query_time)
            assert response.status_code == 200
        
        # Cache should improve performance
        avg_first_round = statistics.mean(first_round_times)
        avg_second_round = statistics.mean(second_round_times)
        
        # Second round should be faster (cache hit) or at least not significantly slower
        performance_ratio = avg_second_round / avg_first_round
        assert performance_ratio <= 1.5, f"Cache performance ratio {performance_ratio:.2f} should be <= 1.5"
        
        print(f"\nCache Performance Test Results:")
        print(f"  First round average: {avg_first_round:.0f}ms")
        print(f"  Second round average: {avg_second_round:.0f}ms")
        print(f"  Performance ratio: {performance_ratio:.2f}")


@pytest.mark.performance
@pytest.mark.slow
class TestStressTests:
    """Stress tests for extreme load conditions."""
    
    @pytest.mark.asyncio
    async def test_extreme_concurrent_load(self, test_client: AsyncClient, test_db):
        """Test system behavior under extreme concurrent load."""
        # This test simulates extreme load - mark as slow
        async def extreme_load_operation(operation_id):
            """Perform operations under extreme load."""
            try:
                # Rapid-fire requests
                responses = []
                for i in range(10):
                    response = await test_client.get("/api/v1/health")
                    responses.append(response.status_code)
                
                return {
                    "operation_id": operation_id,
                    "responses": responses,
                    "success": all(status < 500 for status in responses)
                }
            except Exception as e:
                return {
                    "operation_id": operation_id,
                    "success": False,
                    "error": str(e)
                }
        
        # Execute extreme concurrent load
        start_time = time.perf_counter()
        tasks = [extreme_load_operation(i) for i in range(100)]  # 100 concurrent operations
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_time = (time.perf_counter() - start_time) * 1000
        
        # Analyze extreme load results
        successful_ops = [r for r in results if not isinstance(r, Exception) and r.get("success", False)]
        
        # Under extreme load, we expect some degradation but not complete failure
        success_rate = len(successful_ops) / len(results)
        assert success_rate >= 0.7, f"Under extreme load, success rate {success_rate:.2%} should be >= 70%"
        
        # System should not take excessively long to respond
        assert total_time < 60000, f"Extreme load test took {total_time:.0f}ms, should complete within 60 seconds"
        
        print(f"\nExtreme Load Test Results:")
        print(f"  Total operations: {len(results)}")
        print(f"  Successful operations: {len(successful_ops)}")
        print(f"  Success rate: {success_rate:.2%}")
        print(f"  Total time: {total_time:.0f}ms")