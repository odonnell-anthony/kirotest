"""
Security tests for memory leak detection and resource monitoring.
"""
import pytest
import asyncio
import gc
import time
import psutil
import os
from httpx import AsyncClient

from tests.conftest import UserFactory, DocumentFactory


@pytest.mark.security
class TestMemoryLeakDetection:
    """Test memory leak detection and prevention."""
    
    @pytest.mark.asyncio
    async def test_memory_leak_in_document_operations(self, test_client: AsyncClient, test_db):
        """Test for memory leaks in document operations."""
        process = psutil.Process(os.getpid())
        
        # Get baseline memory usage
        gc.collect()  # Force garbage collection
        baseline_memory = process.memory_info().rss
        
        # Create user for testing
        user = await UserFactory.create_and_save_user(test_db, username="memory_test_user")
        
        # Mock user authentication
        async def mock_user():
            return user
        
        from app.main import app
        from app.core.auth import get_current_user
        app.dependency_overrides[get_current_user] = mock_user
        
        # Perform many document operations
        created_documents = []
        
        for i in range(100):  # Create 100 documents
            doc_data = {
                "title": f"Memory Test Document {i}",
                "content": f"# Document {i}\n\n" + "Content line. " * 100,  # ~1KB content
                "folder_path": f"/memory-test-{i % 10}/",
                "tags": [f"tag-{i % 5}", f"category-{i % 3}"]
            }
            
            response = await test_client.post("/api/v1/documents", json=doc_data)
            if response.status_code == 201:
                document = response.json()
                created_documents.append(document["id"])
            
            # Update some documents
            if i > 0 and i % 10 == 0:
                doc_id = created_documents[i // 10]
                update_data = {
                    "content": f"Updated content for document {i} " + "Updated line. " * 50
                }
                await test_client.put(f"/api/v1/documents/{doc_id}", json=update_data)
            
            # Search operations
            if i % 20 == 0:
                await test_client.get(f"/api/v1/search?q=memory test {i}")
                await test_client.get(f"/api/v1/search/autocomplete?q=tag-{i % 5}")
        
        # Force garbage collection
        gc.collect()
        await asyncio.sleep(0.1)  # Allow async cleanup
        
        # Measure memory after operations
        after_operations_memory = process.memory_info().rss
        memory_increase = after_operations_memory - baseline_memory
        memory_increase_mb = memory_increase / 1024 / 1024
        
        # Delete all created documents
        for doc_id in created_documents:
            await test_client.delete(f"/api/v1/documents/{doc_id}")
        
        # Force garbage collection again
        gc.collect()
        await asyncio.sleep(0.1)
        
        # Measure memory after cleanup
        after_cleanup_memory = process.memory_info().rss
        cleanup_memory_decrease = after_operations_memory - after_cleanup_memory
        cleanup_decrease_mb = cleanup_memory_decrease / 1024 / 1024
        
        # Memory should not increase excessively
        assert memory_increase_mb < 200, f"Memory increased by {memory_increase_mb:.1f}MB, should be < 200MB"
        
        # Memory should decrease after cleanup (indicating proper cleanup)
        assert cleanup_decrease_mb > 0 or memory_increase_mb < 50, \
            f"Memory should decrease after cleanup or initial increase should be minimal"
        
        print(f"\nMemory Leak Test Results:")
        print(f"  Baseline memory: {baseline_memory / 1024 / 1024:.1f}MB")
        print(f"  After operations: {after_operations_memory / 1024 / 1024:.1f}MB")
        print(f"  After cleanup: {after_cleanup_memory / 1024 / 1024:.1f}MB")
        print(f"  Memory increase: {memory_increase_mb:.1f}MB")
        print(f"  Memory recovered: {cleanup_decrease_mb:.1f}MB")
        
        # Clean up
        app.dependency_overrides.clear()
    
    @pytest.mark.asyncio
    async def test_connection_pool_leak(self, test_client: AsyncClient, test_db):
        """Test for database connection pool leaks."""
        # Monitor database connections
        initial_connections = len(test_db.get_bind().pool.checkedout())
        
        async def database_operation(operation_id):
            """Perform database operation that might leak connections."""
            try:
                user = await UserFactory.create_and_save_user(
                    test_db, 
                    username=f"conn_test_user_{operation_id}"
                )
                
                # Create and query documents
                for i in range(5):
                    doc = await DocumentFactory.create_and_save_document(
                        test_db,
                        title=f"Connection Test Doc {operation_id}-{i}",
                        author_id=user.id
                    )
                
                # Perform queries
                from sqlalchemy import select
                from app.models.document import Document
                
                stmt = select(Document).where(Document.author_id == user.id)
                result = await test_db.execute(stmt)
                documents = result.scalars().all()
                
                return len(documents)
                
            except Exception as e:
                print(f"Database operation {operation_id} failed: {e}")
                return 0
        
        # Perform many concurrent database operations
        tasks = [database_operation(i) for i in range(50)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Check connection pool after operations
        await asyncio.sleep(0.5)  # Allow connections to be returned
        final_connections = len(test_db.get_bind().pool.checkedout())
        
        # Connection pool should not leak
        connection_leak = final_connections - initial_connections
        assert connection_leak <= 5, f"Connection pool leaked {connection_leak} connections"
        
        print(f"\nConnection Pool Test Results:")
        print(f"  Initial connections: {initial_connections}")
        print(f"  Final connections: {final_connections}")
        print(f"  Connection leak: {connection_leak}")
    
    @pytest.mark.asyncio
    async def test_file_handle_leak(self, test_client: AsyncClient):
        """Test for file handle leaks during file operations."""
        process = psutil.Process(os.getpid())
        
        # Get initial file descriptor count
        try:
            initial_fds = process.num_fds()
        except AttributeError:
            # Windows doesn't have num_fds, use num_handles
            initial_fds = process.num_handles()
        
        # Perform many file operations
        uploaded_files = []
        
        for i in range(50):
            # Upload file
            file_content = f"File content for handle test {i}. " * 100  # ~3KB file
            files = {"file": (f"handle_test_{i}.txt", file_content.encode(), "text/plain")}
            data = {"folder_path": "/handle-test/"}
            
            response = await test_client.post("/api/v1/files/upload", files=files, data=data)
            if response.status_code == 201:
                file_data = response.json()
                uploaded_files.append(file_data["file_id"])
                
                # Download file immediately
                download_response = await test_client.get(f"/api/v1/files/{file_data['file_id']}")
                assert download_response.status_code == 200
        
        # Allow file handles to be closed
        await asyncio.sleep(0.5)
        
        # Get final file descriptor count
        try:
            final_fds = process.num_fds()
        except AttributeError:
            final_fds = process.num_handles()
        
        # Clean up uploaded files
        for file_id in uploaded_files:
            await test_client.delete(f"/api/v1/files/{file_id}")
        
        # File descriptor count should not increase significantly
        fd_increase = final_fds - initial_fds
        assert fd_increase < 20, f"File descriptor count increased by {fd_increase}, possible file handle leak"
        
        print(f"\nFile Handle Test Results:")
        print(f"  Initial file descriptors: {initial_fds}")
        print(f"  Final file descriptors: {final_fds}")
        print(f"  File descriptor increase: {fd_increase}")
    
    @pytest.mark.asyncio
    async def test_cache_memory_leak(self, test_client: AsyncClient, test_db):
        """Test for memory leaks in caching systems."""
        process = psutil.Process(os.getpid())
        
        # Get baseline memory
        gc.collect()
        baseline_memory = process.memory_info().rss
        
        # Create searchable content
        user = await UserFactory.create_and_save_user(test_db, username="cache_test_user")
        
        # Create documents for caching
        for i in range(100):
            await DocumentFactory.create_and_save_document(
                test_db,
                title=f"Cache Test Document {i}",
                content=f"Searchable content for cache test {i}. " * 20,
                author_id=user.id
            )
        
        # Perform many search operations (should populate cache)
        search_terms = [
            "cache", "test", "document", "content", "searchable",
            "memory", "leak", "performance", "system", "application"
        ]
        
        for round_num in range(10):  # 10 rounds of searches
            for term in search_terms:
                # Search operations
                await test_client.get(f"/api/v1/search?q={term}")
                await test_client.get(f"/api/v1/search?q={term} {round_num}")
                
                # Autocomplete operations
                await test_client.get(f"/api/v1/search/autocomplete?q={term[:3]}")
                
                # Tag operations
                await test_client.get("/api/v1/tags")
        
        # Force garbage collection
        gc.collect()
        await asyncio.sleep(0.1)
        
        # Measure memory after cache operations
        after_cache_memory = process.memory_info().rss
        cache_memory_increase = after_cache_memory - baseline_memory
        cache_increase_mb = cache_memory_increase / 1024 / 1024
        
        # Cache memory increase should be reasonable
        assert cache_increase_mb < 300, f"Cache memory increased by {cache_increase_mb:.1f}MB, should be < 300MB"
        
        print(f"\nCache Memory Test Results:")
        print(f"  Baseline memory: {baseline_memory / 1024 / 1024:.1f}MB")
        print(f"  After cache operations: {after_cache_memory / 1024 / 1024:.1f}MB")
        print(f"  Cache memory increase: {cache_increase_mb:.1f}MB")


@pytest.mark.security
class TestResourceMonitoring:
    """Test resource usage monitoring and limits."""
    
    @pytest.mark.asyncio
    async def test_cpu_usage_monitoring(self, test_client: AsyncClient, test_db):
        """Test CPU usage monitoring during intensive operations."""
        import psutil
        
        # Monitor CPU usage
        cpu_measurements = []
        
        async def cpu_intensive_operation():
            """Perform CPU-intensive operations."""
            # Create complex search operations
            user = await UserFactory.create_and_save_user(test_db, username="cpu_monitor_user")
            
            # Create documents with complex content
            for i in range(50):
                complex_content = f"# Document {i}\n\n"
                for j in range(100):
                    complex_content += f"Line {j} with keywords: python javascript database api framework development. "
                
                await DocumentFactory.create_and_save_document(
                    test_db,
                    title=f"CPU Monitor Document {i}",
                    content=complex_content,
                    author_id=user.id
                )
            
            # Perform intensive search operations
            search_queries = [
                "python javascript database",
                "api framework development",
                "keywords line document",
                "complex content search"
            ]
            
            for _ in range(20):
                for query in search_queries:
                    await test_client.get(f"/api/v1/search?q={query}")
        
        # Measure CPU usage before operation
        initial_cpu = psutil.cpu_percent(interval=1)
        
        # Perform CPU-intensive operation
        start_time = time.perf_counter()
        await cpu_intensive_operation()
        operation_time = (time.perf_counter() - start_time) * 1000
        
        # Measure CPU usage after operation
        final_cpu = psutil.cpu_percent(interval=1)
        
        # CPU usage should be reasonable
        assert operation_time < 60000, f"CPU intensive operation took {operation_time:.0f}ms, should be < 60s"
        
        print(f"\nCPU Usage Monitoring Results:")
        print(f"  Operation time: {operation_time:.0f}ms")
        print(f"  Initial CPU: {initial_cpu:.1f}%")
        print(f"  Final CPU: {final_cpu:.1f}%")
    
    @pytest.mark.asyncio
    async def test_disk_usage_monitoring(self, test_client: AsyncClient):
        """Test disk usage monitoring during file operations."""
        import shutil
        
        # Get initial disk usage
        disk_usage_before = shutil.disk_usage("/tmp")
        
        # Perform disk-intensive operations
        uploaded_files = []
        total_uploaded_size = 0
        
        for i in range(20):
            # Create files of different sizes
            file_size = 1024 * (i + 1)  # 1KB to 20KB
            file_content = b"x" * file_size
            total_uploaded_size += file_size
            
            files = {"file": (f"disk_test_{i}.txt", file_content, "text/plain")}
            data = {"folder_path": "/disk-test/"}
            
            response = await test_client.post("/api/v1/files/upload", files=files, data=data)
            if response.status_code == 201:
                file_data = response.json()
                uploaded_files.append(file_data["file_id"])
        
        # Get disk usage after uploads
        disk_usage_after = shutil.disk_usage("/tmp")
        
        # Clean up files
        for file_id in uploaded_files:
            await test_client.delete(f"/api/v1/files/{file_id}")
        
        # Disk usage increase should be reasonable
        disk_increase = disk_usage_before.used - disk_usage_after.used
        
        print(f"\nDisk Usage Monitoring Results:")
        print(f"  Total uploaded size: {total_uploaded_size / 1024:.1f}KB")
        print(f"  Files uploaded: {len(uploaded_files)}")
        print(f"  Disk usage change: {disk_increase / 1024:.1f}KB")
    
    @pytest.mark.asyncio
    async def test_network_resource_monitoring(self, test_client: AsyncClient):
        """Test network resource usage monitoring."""
        import psutil
        
        # Get initial network stats
        net_io_before = psutil.net_io_counters()
        
        # Perform network-intensive operations
        operations = []
        
        for i in range(100):
            # API calls that generate network traffic
            operations.extend([
                test_client.get("/api/v1/health"),
                test_client.get("/api/v1/search?q=network"),
                test_client.get("/api/v1/tags"),
                test_client.get("/api/v1/documents?page=1&size=10")
            ])
        
        # Execute all operations
        responses = await asyncio.gather(*operations, return_exceptions=True)
        
        # Get network stats after operations
        net_io_after = psutil.net_io_counters()
        
        # Calculate network usage
        bytes_sent = net_io_after.bytes_sent - net_io_before.bytes_sent
        bytes_recv = net_io_after.bytes_recv - net_io_before.bytes_recv
        
        # Network usage should be reasonable for the number of operations
        successful_responses = len([r for r in responses if not isinstance(r, Exception)])
        
        print(f"\nNetwork Resource Monitoring Results:")
        print(f"  Operations performed: {len(operations)}")
        print(f"  Successful responses: {successful_responses}")
        print(f"  Bytes sent: {bytes_sent}")
        print(f"  Bytes received: {bytes_recv}")
        print(f"  Average bytes per operation: {(bytes_sent + bytes_recv) / len(operations):.1f}")


@pytest.mark.security
@pytest.mark.slow
class TestLongRunningResourceTests:
    """Long-running tests for resource leak detection."""
    
    @pytest.mark.asyncio
    async def test_long_running_memory_stability(self, test_client: AsyncClient, test_db):
        """Test memory stability over extended period."""
        process = psutil.Process(os.getpid())
        
        # Record memory usage over time
        memory_measurements = []
        
        # Create user for testing
        user = await UserFactory.create_and_save_user(test_db, username="longrun_user")
        
        # Run operations for extended period
        for cycle in range(20):  # 20 cycles
            cycle_start_memory = process.memory_info().rss
            
            # Perform various operations
            for i in range(10):
                # Document operations
                doc_data = {
                    "title": f"Long Run Document {cycle}-{i}",
                    "content": f"Content for long running test {cycle}-{i}. " * 50,
                    "folder_path": f"/longrun-{cycle}/",
                    "author_id": user.id
                }
                
                doc_response = await test_client.post("/api/v1/documents", json=doc_data)
                if doc_response.status_code == 201:
                    document = doc_response.json()
                    
                    # Update document
                    update_data = {"content": f"Updated content {cycle}-{i}. " * 30}
                    await test_client.put(f"/api/v1/documents/{document['id']}", json=update_data)
                    
                    # Search operations
                    await test_client.get(f"/api/v1/search?q=long run {cycle}")
                    
                    # Delete document
                    await test_client.delete(f"/api/v1/documents/{document['id']}")
            
            # Force garbage collection
            gc.collect()
            await asyncio.sleep(0.1)
            
            cycle_end_memory = process.memory_info().rss
            memory_measurements.append({
                "cycle": cycle,
                "memory_mb": cycle_end_memory / 1024 / 1024,
                "increase_mb": (cycle_end_memory - cycle_start_memory) / 1024 / 1024
            })
        
        # Analyze memory stability
        memory_values = [m["memory_mb"] for m in memory_measurements]
        memory_increases = [m["increase_mb"] for m in memory_measurements]
        
        # Memory should be relatively stable (not continuously increasing)
        max_memory = max(memory_values)
        min_memory = min(memory_values)
        memory_variance = max_memory - min_memory
        
        assert memory_variance < 200, f"Memory variance {memory_variance:.1f}MB too high, possible memory leak"
        
        # Average memory increase per cycle should be minimal
        avg_increase = sum(memory_increases) / len(memory_increases)
        assert avg_increase < 5, f"Average memory increase per cycle {avg_increase:.1f}MB too high"
        
        print(f"\nLong Running Memory Stability Results:")
        print(f"  Cycles completed: {len(memory_measurements)}")
        print(f"  Memory variance: {memory_variance:.1f}MB")
        print(f"  Average increase per cycle: {avg_increase:.1f}MB")
        print(f"  Min memory: {min_memory:.1f}MB")
        print(f"  Max memory: {max_memory:.1f}MB")