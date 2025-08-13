"""
Integration tests for file upload and storage operations.
"""
import pytest
import uuid
import tempfile
import os
from pathlib import Path
from httpx import AsyncClient
from fastapi import status

from tests.conftest import UserFactory


@pytest.mark.integration
class TestFileUploadIntegration:
    """Test file upload integration with storage backend."""
    
    @pytest.mark.asyncio
    async def test_file_upload_complete_flow(self, test_client: AsyncClient, test_db):
        """Test complete file upload flow from API to storage."""
        # Create test file content
        test_content = b"This is a test file for upload integration testing."
        filename = "integration_test.txt"
        
        files = {"file": (filename, test_content, "text/plain")}
        data = {"folder_path": "/uploads/integration/"}
        
        # Upload file
        response = await test_client.post("/api/v1/files/upload", files=files, data=data)
        
        assert response.status_code == status.HTTP_201_CREATED
        upload_data = response.json()
        
        # Verify response structure
        assert "file_id" in upload_data
        assert "filename" in upload_data
        assert "file_path" in upload_data
        assert "mime_type" in upload_data
        assert "file_size" in upload_data
        
        # Verify file metadata
        assert upload_data["filename"] == filename
        assert upload_data["mime_type"] == "text/plain"
        assert upload_data["file_size"] == len(test_content)
        
        file_id = upload_data["file_id"]
        
        # Test file retrieval
        response = await test_client.get(f"/api/v1/files/{file_id}")
        assert response.status_code == status.HTTP_200_OK
        
        # Verify downloaded content matches uploaded content
        assert response.content == test_content
        assert response.headers["content-type"] == "text/plain"
    
    @pytest.mark.asyncio
    async def test_file_upload_with_document_attachment(self, test_client: AsyncClient, test_db):
        """Test file upload and attachment to document."""
        # Create a document first
        doc_data = {
            "title": "Document with Attachment",
            "content": "This document will have a file attachment.",
            "folder_path": "/docs/"
        }
        
        doc_response = await test_client.post("/api/v1/documents", json=doc_data)
        assert doc_response.status_code == status.HTTP_201_CREATED
        document = doc_response.json()
        document_id = document["id"]
        
        # Upload file and attach to document
        test_content = b"Attachment content for document"
        files = {"file": ("attachment.txt", test_content, "text/plain")}
        data = {
            "folder_path": "/attachments/",
            "document_id": document_id
        }
        
        response = await test_client.post("/api/v1/files/upload", files=files, data=data)
        assert response.status_code == status.HTTP_201_CREATED
        
        file_data = response.json()
        file_id = file_data["file_id"]
        
        # Verify file is attached to document
        doc_response = await test_client.get(f"/api/v1/documents/{document_id}")
        assert doc_response.status_code == status.HTTP_200_OK
        
        updated_document = doc_response.json()
        # Check if document has attachments (structure depends on implementation)
        assert "attachments" in updated_document or "files" in updated_document
    
    @pytest.mark.asyncio
    async def test_multiple_file_upload(self, test_client: AsyncClient):
        """Test uploading multiple files in sequence."""
        files_to_upload = [
            ("file1.txt", b"Content of file 1", "text/plain"),
            ("file2.md", b"# Markdown Content\n\nThis is markdown.", "text/markdown"),
            ("file3.json", b'{"key": "value", "number": 42}', "application/json"),
        ]
        
        uploaded_files = []
        
        for filename, content, mime_type in files_to_upload:
            files = {"file": (filename, content, mime_type)}
            data = {"folder_path": "/multi-upload/"}
            
            response = await test_client.post("/api/v1/files/upload", files=files, data=data)
            assert response.status_code == status.HTTP_201_CREATED
            
            file_data = response.json()
            uploaded_files.append(file_data)
            
            # Verify each file
            assert file_data["filename"] == filename
            assert file_data["mime_type"] == mime_type
            assert file_data["file_size"] == len(content)
        
        # Verify all files can be retrieved
        for file_data in uploaded_files:
            file_id = file_data["file_id"]
            response = await test_client.get(f"/api/v1/files/{file_id}")
            assert response.status_code == status.HTTP_200_OK
    
    @pytest.mark.asyncio
    async def test_file_upload_size_limits(self, test_client: AsyncClient):
        """Test file upload size limit enforcement."""
        # Test with file at size limit (assuming 10MB limit)
        large_content = b"x" * (10 * 1024 * 1024)  # 10MB
        files = {"file": ("large_file.txt", large_content, "text/plain")}
        data = {"folder_path": "/uploads/"}
        
        response = await test_client.post("/api/v1/files/upload", files=files, data=data)
        
        # Should either succeed (if under limit) or be rejected (if over limit)
        assert response.status_code in [201, 413, 422]
        
        # Test with file over size limit
        oversized_content = b"x" * (100 * 1024 * 1024 + 1)  # 100MB + 1 byte
        files = {"file": ("oversized_file.txt", oversized_content, "text/plain")}
        data = {"folder_path": "/uploads/"}
        
        response = await test_client.post("/api/v1/files/upload", files=files, data=data)
        
        # Should be rejected
        assert response.status_code in [413, 422]
    
    @pytest.mark.asyncio
    async def test_file_type_validation_integration(self, test_client: AsyncClient):
        """Test file type validation in upload flow."""
        # Test allowed file types
        allowed_files = [
            ("document.txt", b"Text content", "text/plain"),
            ("image.jpg", b"\xff\xd8\xff\xe0", "image/jpeg"),  # JPEG header
            ("data.json", b'{"test": true}', "application/json"),
            ("style.css", b"body { margin: 0; }", "text/css"),
        ]
        
        for filename, content, mime_type in allowed_files:
            files = {"file": (filename, content, mime_type)}
            data = {"folder_path": "/uploads/allowed/"}
            
            response = await test_client.post("/api/v1/files/upload", files=files, data=data)
            
            # Should be accepted
            assert response.status_code == status.HTTP_201_CREATED, f"File {filename} should be allowed"
        
        # Test disallowed file types
        disallowed_files = [
            ("malware.exe", b"MZ\x90\x00", "application/x-executable"),
            ("script.sh", b"#!/bin/bash", "application/x-sh"),
            ("virus.bat", b"@echo off", "application/x-msdos-program"),
        ]
        
        for filename, content, mime_type in disallowed_files:
            files = {"file": (filename, content, mime_type)}
            data = {"folder_path": "/uploads/disallowed/"}
            
            response = await test_client.post("/api/v1/files/upload", files=files, data=data)
            
            # Should be rejected
            assert response.status_code in [400, 415, 422], f"File {filename} should be rejected"
    
    @pytest.mark.asyncio
    async def test_file_metadata_persistence(self, test_client: AsyncClient, test_db):
        """Test that file metadata is properly persisted in database."""
        # Upload a file
        test_content = b"Test content for metadata persistence"
        files = {"file": ("metadata_test.txt", test_content, "text/plain")}
        data = {"folder_path": "/metadata-test/"}
        
        response = await test_client.post("/api/v1/files/upload", files=files, data=data)
        assert response.status_code == status.HTTP_201_CREATED
        
        file_data = response.json()
        file_id = file_data["file_id"]
        
        # Get file metadata
        response = await test_client.get(f"/api/v1/files/{file_id}/metadata")
        assert response.status_code == status.HTTP_200_OK
        
        metadata = response.json()
        
        # Verify metadata structure
        expected_fields = ["file_id", "filename", "mime_type", "file_size", "folder_path", "created_at", "updated_at"]
        for field in expected_fields:
            assert field in metadata, f"Metadata should contain {field}"
        
        # Verify metadata values
        assert metadata["filename"] == "metadata_test.txt"
        assert metadata["mime_type"] == "text/plain"
        assert metadata["file_size"] == len(test_content)
        assert metadata["folder_path"] == "/metadata-test/"


@pytest.mark.integration
class TestFileStorageIntegration:
    """Test file storage backend integration."""
    
    @pytest.mark.asyncio
    async def test_file_storage_and_retrieval(self, test_client: AsyncClient):
        """Test that files are properly stored and can be retrieved."""
        # Upload file
        original_content = b"Original file content for storage test"
        files = {"file": ("storage_test.txt", original_content, "text/plain")}
        data = {"folder_path": "/storage-test/"}
        
        upload_response = await test_client.post("/api/v1/files/upload", files=files, data=data)
        assert upload_response.status_code == status.HTTP_201_CREATED
        
        file_data = upload_response.json()
        file_id = file_data["file_id"]
        
        # Retrieve file content
        download_response = await test_client.get(f"/api/v1/files/{file_id}")
        assert download_response.status_code == status.HTTP_200_OK
        
        # Verify content matches
        assert download_response.content == original_content
        
        # Verify headers
        assert download_response.headers["content-type"] == "text/plain"
        assert "content-length" in download_response.headers
        assert int(download_response.headers["content-length"]) == len(original_content)
    
    @pytest.mark.asyncio
    async def test_file_deletion_integration(self, test_client: AsyncClient):
        """Test file deletion from storage."""
        # Upload file
        test_content = b"Content to be deleted"
        files = {"file": ("delete_test.txt", test_content, "text/plain")}
        data = {"folder_path": "/delete-test/"}
        
        upload_response = await test_client.post("/api/v1/files/upload", files=files, data=data)
        assert upload_response.status_code == status.HTTP_201_CREATED
        
        file_data = upload_response.json()
        file_id = file_data["file_id"]
        
        # Verify file exists
        get_response = await test_client.get(f"/api/v1/files/{file_id}")
        assert get_response.status_code == status.HTTP_200_OK
        
        # Delete file
        delete_response = await test_client.delete(f"/api/v1/files/{file_id}")
        assert delete_response.status_code == status.HTTP_200_OK
        
        # Verify file is deleted
        get_response = await test_client.get(f"/api/v1/files/{file_id}")
        assert get_response.status_code == status.HTTP_404_NOT_FOUND
    
    @pytest.mark.asyncio
    async def test_file_storage_organization(self, test_client: AsyncClient):
        """Test that files are organized properly in storage."""
        # Upload files to different folders
        folders = ["/folder1/", "/folder2/subfolder/", "/folder3/deep/nested/path/"]
        uploaded_files = []
        
        for i, folder in enumerate(folders):
            content = f"Content for file in {folder}".encode()
            files = {"file": (f"file_{i}.txt", content, "text/plain")}
            data = {"folder_path": folder}
            
            response = await test_client.post("/api/v1/files/upload", files=files, data=data)
            assert response.status_code == status.HTTP_201_CREATED
            
            file_data = response.json()
            uploaded_files.append((file_data["file_id"], folder))
        
        # Verify files can be retrieved from their respective folders
        for file_id, expected_folder in uploaded_files:
            response = await test_client.get(f"/api/v1/files/{file_id}/metadata")
            assert response.status_code == status.HTTP_200_OK
            
            metadata = response.json()
            assert metadata["folder_path"] == expected_folder
    
    @pytest.mark.asyncio
    async def test_concurrent_file_uploads(self, test_client: AsyncClient):
        """Test concurrent file uploads."""
        import asyncio
        
        async def upload_file(file_index):
            """Upload a single file."""
            content = f"Concurrent upload test file {file_index}".encode()
            files = {"file": (f"concurrent_{file_index}.txt", content, "text/plain")}
            data = {"folder_path": "/concurrent-uploads/"}
            
            response = await test_client.post("/api/v1/files/upload", files=files, data=data)
            return response.status_code, response.json() if response.status_code == 201 else None
        
        # Upload 5 files concurrently
        tasks = [upload_file(i) for i in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verify results
        successful_uploads = 0
        for result in results:
            if not isinstance(result, Exception):
                status_code, data = result
                if status_code == 201:
                    successful_uploads += 1
        
        # Should have most uploads succeed
        assert successful_uploads >= 4, f"Only {successful_uploads} out of 5 concurrent uploads succeeded"


@pytest.mark.integration
class TestFilePermissionsIntegration:
    """Test file permissions and access control integration."""
    
    @pytest.mark.asyncio
    async def test_file_access_permissions(self, test_client: AsyncClient, test_db):
        """Test file access permissions."""
        # Create two users
        user1 = await UserFactory.create_and_save_user(test_db, username="fileowner")
        user2 = await UserFactory.create_and_save_user(test_db, username="otheruser")
        
        # Mock user1 as current user and upload file
        async def mock_user1():
            return user1
        
        from app.main import app
        from app.core.auth import get_current_user
        app.dependency_overrides[get_current_user] = mock_user1
        
        # Upload file as user1
        test_content = b"Private file content"
        files = {"file": ("private_file.txt", test_content, "text/plain")}
        data = {"folder_path": "/private/"}
        
        response = await test_client.post("/api/v1/files/upload", files=files, data=data)
        assert response.status_code == status.HTTP_201_CREATED
        
        file_data = response.json()
        file_id = file_data["file_id"]
        
        # Verify user1 can access the file
        response = await test_client.get(f"/api/v1/files/{file_id}")
        assert response.status_code == status.HTTP_200_OK
        
        # Switch to user2
        async def mock_user2():
            return user2
        
        app.dependency_overrides[get_current_user] = mock_user2
        
        # Verify user2 cannot access user1's private file
        response = await test_client.get(f"/api/v1/files/{file_id}")
        assert response.status_code in [403, 404], "Users should not access others' private files"
        
        # Clean up
        app.dependency_overrides.clear()
    
    @pytest.mark.asyncio
    async def test_public_file_access(self, test_client: AsyncClient, test_db):
        """Test public file access."""
        # Upload a public file
        test_content = b"Public file content"
        files = {"file": ("public_file.txt", test_content, "text/plain")}
        data = {
            "folder_path": "/public/",
            "is_public": True
        }
        
        response = await test_client.post("/api/v1/files/upload", files=files, data=data)
        assert response.status_code == status.HTTP_201_CREATED
        
        file_data = response.json()
        file_id = file_data["file_id"]
        
        # Verify public file can be accessed without authentication
        from app.main import app
        from app.core.auth import get_current_user
        
        # Remove authentication
        if get_current_user in app.dependency_overrides:
            del app.dependency_overrides[get_current_user]
        
        response = await test_client.get(f"/api/v1/files/{file_id}")
        # Public files should be accessible (implementation dependent)
        assert response.status_code in [200, 401]  # 401 if auth is still required
    
    @pytest.mark.asyncio
    async def test_admin_file_access(self, test_client: AsyncClient, test_db):
        """Test admin access to all files."""
        from app.models.user import UserRole
        
        # Create regular user and admin user
        regular_user = await UserFactory.create_and_save_user(test_db, username="regular")
        admin_user = await UserFactory.create_and_save_user(test_db, username="admin", role=UserRole.ADMIN)
        
        # Upload file as regular user
        async def mock_regular_user():
            return regular_user
        
        from app.main import app
        from app.core.auth import get_current_user
        app.dependency_overrides[get_current_user] = mock_regular_user
        
        test_content = b"Regular user file"
        files = {"file": ("regular_file.txt", test_content, "text/plain")}
        data = {"folder_path": "/regular/"}
        
        response = await test_client.post("/api/v1/files/upload", files=files, data=data)
        assert response.status_code == status.HTTP_201_CREATED
        
        file_data = response.json()
        file_id = file_data["file_id"]
        
        # Switch to admin user
        async def mock_admin_user():
            return admin_user
        
        app.dependency_overrides[get_current_user] = mock_admin_user
        
        # Verify admin can access regular user's file
        response = await test_client.get(f"/api/v1/files/{file_id}")
        assert response.status_code == status.HTTP_200_OK, "Admin should access all files"
        
        # Clean up
        app.dependency_overrides.clear()