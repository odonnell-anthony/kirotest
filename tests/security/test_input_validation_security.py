"""
Security tests for input validation and sanitization.
"""
import pytest
from httpx import AsyncClient

from tests.conftest import UserFactory, DocumentFactory


@pytest.mark.security
class TestInputSanitizationSecurity:
    """Test input sanitization security measures."""
    
    @pytest.mark.asyncio
    async def test_document_content_sanitization(self, test_client: AsyncClient, security_test_data):
        """Test that document content is properly sanitized."""
        xss_payloads = security_test_data["xss_payloads"]
        
        for payload in xss_payloads:
            doc_data = {
                "title": "Security Test Document",
                "content": f"# Test Content\n\n{payload}\n\nSafe content after payload.",
                "folder_path": "/security-test/"
            }
            
            response = await test_client.post("/api/v1/documents", json=doc_data)
            
            if response.status_code == 201:
                data = response.json()
                content = data["content"]
                
                # Verify dangerous content is removed or escaped
                assert "<script>" not in content.lower()
                assert "javascript:" not in content.lower()
                assert "onerror=" not in content.lower()
                assert "onload=" not in content.lower()
                
                # Verify safe content is preserved
                assert "Safe content after payload" in content
    
    @pytest.mark.asyncio
    async def test_document_title_sanitization(self, test_client: AsyncClient, security_test_data):
        """Test that document titles are properly sanitized."""
        xss_payloads = security_test_data["xss_payloads"]
        
        for payload in xss_payloads:
            doc_data = {
                "title": f"Test Title {payload}",
                "content": "Safe content",
                "folder_path": "/security-test/"
            }
            
            response = await test_client.post("/api/v1/documents", json=doc_data)
            
            if response.status_code == 201:
                data = response.json()
                title = data["title"]
                
                # Verify dangerous content is removed from title
                assert "<script>" not in title.lower()
                assert "javascript:" not in title.lower()
                assert "onerror=" not in title.lower()
                
                # Verify safe part of title is preserved
                assert "Test Title" in title
    
    @pytest.mark.asyncio
    async def test_tag_name_sanitization(self, test_client: AsyncClient, security_test_data):
        """Test that tag names are properly sanitized."""
        xss_payloads = security_test_data["xss_payloads"]
        
        for payload in xss_payloads:
            tag_data = {
                "name": f"tag-{payload}",
                "description": "Test tag with malicious content",
                "color": "#007acc"
            }
            
            response = await test_client.post("/api/v1/tags", json=tag_data)
            
            if response.status_code == 201:
                data = response.json()
                name = data["name"]
                
                # Verify dangerous content is removed from tag name
                assert "<script>" not in name.lower()
                assert "javascript:" not in name.lower()
                assert "onerror=" not in name.lower()
                
                # Tag names should be normalized (lowercase, alphanumeric + hyphens)
                assert name.islower() or name.replace("-", "").replace("_", "").isalnum()
    
    @pytest.mark.asyncio
    async def test_comment_content_sanitization(self, test_client: AsyncClient, test_document, security_test_data):
        """Test that comment content is properly sanitized."""
        xss_payloads = security_test_data["xss_payloads"]
        
        for payload in xss_payloads:
            comment_data = {
                "content": f"This is a comment with malicious content: {payload}",
                "parent_id": None
            }
            
            response = await test_client.post(f"/api/v1/documents/{test_document.id}/comments", json=comment_data)
            
            if response.status_code == 201:
                data = response.json()
                content = data["content"]
                
                # Verify dangerous content is removed
                assert "<script>" not in content.lower()
                assert "javascript:" not in content.lower()
                assert "onerror=" not in content.lower()
                
                # Verify safe content is preserved
                assert "This is a comment" in content
    
    @pytest.mark.asyncio
    async def test_search_query_sanitization(self, test_client: AsyncClient, security_test_data):
        """Test that search queries are properly sanitized."""
        xss_payloads = security_test_data["xss_payloads"]
        sql_payloads = security_test_data["sql_injection_payloads"]
        
        all_payloads = xss_payloads + sql_payloads
        
        for payload in all_payloads:
            # Test search endpoint
            response = await test_client.get(f"/api/v1/search?q={payload}")
            
            # Should not cause server error
            assert response.status_code != 500, f"Search query caused server error: {payload}"
            
            if response.status_code == 200:
                data = response.json()
                
                # Verify response doesn't contain dangerous content
                response_str = str(data).lower()
                assert "<script>" not in response_str
                assert "javascript:" not in response_str
    
    @pytest.mark.asyncio
    async def test_folder_path_validation(self, test_client: AsyncClient, security_test_data):
        """Test that folder paths are properly validated."""
        path_payloads = security_test_data["path_traversal_payloads"]
        
        for payload in path_payloads:
            doc_data = {
                "title": "Test Document",
                "content": "Test content",
                "folder_path": payload
            }
            
            response = await test_client.post("/api/v1/documents", json=doc_data)
            
            # Should reject invalid folder paths
            assert response.status_code in [400, 422], f"Invalid folder path should be rejected: {payload}"
    
    @pytest.mark.asyncio
    async def test_filename_sanitization(self, test_client: AsyncClient):
        """Test that uploaded filenames are properly sanitized."""
        malicious_filenames = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "file<script>alert('xss')</script>.txt",
            "file'; DROP TABLE files; --.txt",
            "file\x00.exe.txt",  # Null byte injection
            "CON.txt",  # Windows reserved name
            "file|rm -rf /.txt",
        ]
        
        for filename in malicious_filenames:
            file_content = b"Test file content"
            files = {"file": (filename, file_content, "text/plain")}
            data = {"folder_path": "/uploads/"}
            
            response = await test_client.post("/api/v1/files/upload", files=files, data=data)
            
            if response.status_code == 201:
                data = response.json()
                stored_filename = data["filename"]
                
                # Verify dangerous characters are removed or escaped
                assert "../" not in stored_filename
                assert "..\\" not in stored_filename
                assert "<script>" not in stored_filename.lower()
                assert "'" not in stored_filename
                assert "\x00" not in stored_filename
                assert "|" not in stored_filename
            else:
                # Should reject malicious filenames
                assert response.status_code in [400, 422], f"Malicious filename should be rejected: {filename}"


@pytest.mark.security
class TestParameterValidationSecurity:
    """Test parameter validation security measures."""
    
    @pytest.mark.asyncio
    async def test_pagination_parameter_validation(self, test_client: AsyncClient):
        """Test that pagination parameters are properly validated."""
        malicious_params = [
            {"page": "-1", "size": "10"},
            {"page": "999999999999999999999", "size": "10"},
            {"page": "1", "size": "-1"},
            {"page": "1", "size": "999999999999999999999"},
            {"page": "'; DROP TABLE documents; --", "size": "10"},
            {"page": "<script>alert('xss')</script>", "size": "10"},
            {"page": "1", "size": "1000000"},  # Extremely large page size
        ]
        
        for params in malicious_params:
            response = await test_client.get("/api/v1/documents", params=params)
            
            # Should not cause server error
            assert response.status_code != 500, f"Malicious pagination params caused error: {params}"
            
            # Should either work with sanitized params or return validation error
            assert response.status_code in [200, 400, 422], f"Unexpected status for params: {params}"
    
    @pytest.mark.asyncio
    async def test_uuid_parameter_validation(self, test_client: AsyncClient):
        """Test that UUID parameters are properly validated."""
        malicious_uuids = [
            "'; DROP TABLE documents; --",
            "<script>alert('xss')</script>",
            "../../../etc/passwd",
            "not-a-uuid",
            "00000000-0000-0000-0000-00000000000g",  # Invalid character
            "00000000-0000-0000-0000-000000000000' OR '1'='1",
        ]
        
        for malicious_uuid in malicious_uuids:
            response = await test_client.get(f"/api/v1/documents/{malicious_uuid}")
            
            # Should not cause server error
            assert response.status_code != 500, f"Malicious UUID caused error: {malicious_uuid}"
            
            # Should return validation error or not found
            assert response.status_code in [400, 404, 422], f"Malicious UUID should be rejected: {malicious_uuid}"
    
    @pytest.mark.asyncio
    async def test_filter_parameter_validation(self, test_client: AsyncClient):
        """Test that filter parameters are properly validated."""
        malicious_filters = [
            {"author_id": "'; DROP TABLE users; --"},
            {"folder_path": "<script>alert('xss')</script>"},
            {"status": "published'; DELETE FROM documents; --"},
            {"tag": "../../../etc/passwd"},
        ]
        
        for filters in malicious_filters:
            response = await test_client.get("/api/v1/documents", params=filters)
            
            # Should not cause server error
            assert response.status_code != 500, f"Malicious filters caused error: {filters}"
            
            # Should either work with sanitized params or return validation error
            assert response.status_code in [200, 400, 422], f"Unexpected status for filters: {filters}"
    
    @pytest.mark.asyncio
    async def test_json_payload_validation(self, test_client: AsyncClient):
        """Test that JSON payloads are properly validated."""
        malicious_payloads = [
            {"title": "x" * 10000},  # Extremely long title
            {"content": "x" * 1000000},  # Extremely long content
            {"folder_path": "x" * 1000},  # Extremely long path
            {"tags": ["tag"] * 1000},  # Too many tags
            {"title": None},  # Null title
            {"content": {"$ne": None}},  # NoSQL injection attempt
        ]
        
        for payload in malicious_payloads:
            response = await test_client.post("/api/v1/documents", json=payload)
            
            # Should not cause server error
            assert response.status_code != 500, f"Malicious payload caused error: {payload}"
            
            # Should return validation error
            assert response.status_code in [400, 422], f"Malicious payload should be rejected: {payload}"


@pytest.mark.security
class TestContentTypeValidationSecurity:
    """Test content type validation security measures."""
    
    @pytest.mark.asyncio
    async def test_file_upload_content_type_validation(self, test_client: AsyncClient):
        """Test that file upload content types are properly validated."""
        malicious_files = [
            ("malicious.exe", b"MZ\x90\x00", "application/x-executable"),
            ("script.sh", b"#!/bin/bash\nrm -rf /", "application/x-sh"),
            ("virus.bat", b"@echo off\ndel /f /q *.*", "application/x-msdos-program"),
            ("payload.php", b"<?php system($_GET['cmd']); ?>", "application/x-php"),
            ("malware.scr", b"malicious screensaver", "application/x-screensaver"),
            ("trojan.com", b"malicious command", "application/x-msdos-program"),
        ]
        
        for filename, content, mime_type in malicious_files:
            files = {"file": (filename, content, mime_type)}
            data = {"folder_path": "/uploads/"}
            
            response = await test_client.post("/api/v1/files/upload", files=files, data=data)
            
            # Should reject dangerous file types
            assert response.status_code in [400, 415, 422], f"Dangerous file type should be rejected: {filename}"
    
    @pytest.mark.asyncio
    async def test_content_type_spoofing_protection(self, test_client: AsyncClient):
        """Test protection against content type spoofing."""
        # Upload executable with text/plain content type
        executable_content = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00"
        files = {"file": ("innocent.txt", executable_content, "text/plain")}
        data = {"folder_path": "/uploads/"}
        
        response = await test_client.post("/api/v1/files/upload", files=files, data=data)
        
        # Should detect actual file type and reject if dangerous
        # (This depends on implementation - might use magic bytes detection)
        if response.status_code == 201:
            # If accepted, verify it's properly handled
            data = response.json()
            assert "file_id" in data
        else:
            # Should be rejected due to content analysis
            assert response.status_code in [400, 415, 422]
    
    @pytest.mark.asyncio
    async def test_json_content_type_enforcement(self, test_client: AsyncClient):
        """Test that JSON endpoints enforce proper content type."""
        # Try to send JSON data with wrong content type
        import json
        
        doc_data = {
            "title": "Test Document",
            "content": "Test content",
            "folder_path": "/test/"
        }
        
        # Send as form data instead of JSON
        response = await test_client.post(
            "/api/v1/documents",
            data=json.dumps(doc_data),
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        # Should reject wrong content type
        assert response.status_code in [400, 415, 422], "Wrong content type should be rejected"
    
    @pytest.mark.asyncio
    async def test_multipart_form_validation(self, test_client: AsyncClient):
        """Test multipart form validation security."""
        # Create malformed multipart data
        malformed_boundary = "----WebKitFormBoundary" + "A" * 1000  # Extremely long boundary
        
        headers = {"Content-Type": f"multipart/form-data; boundary={malformed_boundary}"}
        data = f"--{malformed_boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"test.txt\"\r\n\r\ntest content\r\n--{malformed_boundary}--"
        
        response = await test_client.post("/api/v1/files/upload", content=data, headers=headers)
        
        # Should handle malformed multipart gracefully
        assert response.status_code != 500, "Malformed multipart should not cause server error"
        assert response.status_code in [400, 422], "Malformed multipart should be rejected"


@pytest.mark.security
class TestRateLimitingValidationSecurity:
    """Test rate limiting validation security measures."""
    
    @pytest.mark.asyncio
    async def test_api_rate_limiting(self, test_client: AsyncClient):
        """Test that API endpoints are properly rate limited."""
        # Make rapid requests to a rate-limited endpoint
        responses = []
        
        for i in range(50):  # Make many requests quickly
            response = await test_client.get("/api/v1/search/autocomplete?q=test")
            responses.append(response.status_code)
        
        # Should eventually get rate limited
        rate_limited_count = responses.count(429)  # HTTP 429 Too Many Requests
        
        # Should have some rate limiting (exact threshold depends on configuration)
        assert rate_limited_count > 0, "Rate limiting should kick in with rapid requests"
    
    @pytest.mark.asyncio
    async def test_file_upload_rate_limiting(self, test_client: AsyncClient):
        """Test that file uploads are rate limited."""
        # Make rapid file upload requests
        responses = []
        
        for i in range(20):
            file_content = f"Test file content {i}".encode()
            files = {"file": (f"test{i}.txt", file_content, "text/plain")}
            data = {"folder_path": "/uploads/"}
            
            response = await test_client.post("/api/v1/files/upload", files=files, data=data)
            responses.append(response.status_code)
        
        # Should eventually get rate limited or rejected
        error_responses = [code for code in responses if code >= 400]
        
        # Should have some protection against rapid uploads
        assert len(error_responses) > 0, "Should have some protection against rapid file uploads"
    
    @pytest.mark.asyncio
    async def test_search_rate_limiting(self, test_client: AsyncClient):
        """Test that search endpoints are rate limited."""
        # Make rapid search requests
        responses = []
        
        for i in range(30):
            response = await test_client.get(f"/api/v1/search?q=test{i}")
            responses.append(response.status_code)
        
        # Should eventually get rate limited
        rate_limited_count = responses.count(429)
        
        # Should have some rate limiting for search
        assert rate_limited_count > 0 or responses.count(200) < 30, "Search should be rate limited"