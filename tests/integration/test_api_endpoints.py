"""
Integration tests for API endpoints.
"""
import pytest
import uuid
from httpx import AsyncClient
from fastapi import status

from app.models.user import UserRole
from app.models.document import DocumentStatus
from tests.conftest import UserFactory, DocumentFactory


@pytest.mark.integration
class TestAuthenticationEndpoints:
    """Test authentication API endpoints."""
    
    @pytest.mark.asyncio
    async def test_login_success(self, test_client: AsyncClient, test_user):
        """Test successful login."""
        login_data = {
            "username": test_user.username,
            "password": "test_password"
        }
        
        # Mock password verification
        with pytest.mock.patch('app.services.auth.AuthenticationService.verify_password', return_value=True):
            response = await test_client.post("/api/v1/auth/login", json=login_data)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
    
    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, test_client: AsyncClient):
        """Test login with invalid credentials."""
        login_data = {
            "username": "nonexistent",
            "password": "wrong_password"
        }
        
        response = await test_client.post("/api/v1/auth/login", json=login_data)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        data = response.json()
        assert "Invalid username or password" in data["detail"]
    
    @pytest.mark.asyncio
    async def test_get_current_user_success(self, test_client: AsyncClient, test_user):
        """Test getting current user profile."""
        response = await test_client.get("/api/v1/auth/me")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == str(test_user.id)
        assert data["username"] == test_user.username
        assert data["email"] == test_user.email
    
    @pytest.mark.asyncio
    async def test_logout_success(self, test_client: AsyncClient):
        """Test successful logout."""
        response = await test_client.post("/api/v1/auth/logout")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["message"] == "Successfully logged out"


@pytest.mark.integration
class TestDocumentEndpoints:
    """Test document API endpoints."""
    
    @pytest.mark.asyncio
    async def test_create_document_success(self, test_client: AsyncClient, test_user):
        """Test successful document creation."""
        document_data = {
            "title": "Test Document",
            "content": "# Test Content\n\nThis is a test document.",
            "folder_path": "/test/",
            "tags": ["python", "testing"],
            "status": "published"
        }
        
        response = await test_client.post("/api/v1/documents", json=document_data)
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["title"] == document_data["title"]
        assert data["content"] == document_data["content"]
        assert data["folder_path"] == document_data["folder_path"]
        assert data["author_id"] == str(test_user.id)
    
    @pytest.mark.asyncio
    async def test_create_document_invalid_data(self, test_client: AsyncClient):
        """Test document creation with invalid data."""
        document_data = {
            "title": "",  # Empty title
            "content": "Test content"
        }
        
        response = await test_client.post("/api/v1/documents", json=document_data)
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    @pytest.mark.asyncio
    async def test_get_document_success(self, test_client: AsyncClient, test_document):
        """Test successful document retrieval."""
        response = await test_client.get(f"/api/v1/documents/{test_document.id}")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == str(test_document.id)
        assert data["title"] == test_document.title
        assert data["content"] == test_document.content
    
    @pytest.mark.asyncio
    async def test_get_document_not_found(self, test_client: AsyncClient):
        """Test document retrieval when document doesn't exist."""
        non_existent_id = uuid.uuid4()
        response = await test_client.get(f"/api/v1/documents/{non_existent_id}")
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    @pytest.mark.asyncio
    async def test_update_document_success(self, test_client: AsyncClient, test_document):
        """Test successful document update."""
        update_data = {
            "title": "Updated Document Title",
            "content": "# Updated Content\n\nThis is updated content."
        }
        
        response = await test_client.put(f"/api/v1/documents/{test_document.id}", json=update_data)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["title"] == update_data["title"]
        assert data["content"] == update_data["content"]
    
    @pytest.mark.asyncio
    async def test_delete_document_success(self, test_client: AsyncClient, test_document):
        """Test successful document deletion."""
        response = await test_client.delete(f"/api/v1/documents/{test_document.id}")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
    
    @pytest.mark.asyncio
    async def test_get_documents_list(self, test_client: AsyncClient, test_db):
        """Test getting list of documents."""
        # Create multiple test documents
        user = await UserFactory.create_and_save_user(test_db)
        for i in range(3):
            await DocumentFactory.create_and_save_document(
                test_db, 
                title=f"Test Document {i}",
                author_id=user.id
            )
        
        response = await test_client.get("/api/v1/documents")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["items"]) >= 3
        assert "total" in data
        assert "page" in data
        assert "size" in data
    
    @pytest.mark.asyncio
    async def test_get_documents_by_folder(self, test_client: AsyncClient, test_db):
        """Test getting documents by folder path."""
        user = await UserFactory.create_and_save_user(test_db)
        folder_path = "/test-folder/"
        
        # Create documents in specific folder
        for i in range(2):
            await DocumentFactory.create_and_save_document(
                test_db,
                title=f"Folder Document {i}",
                folder_path=folder_path,
                author_id=user.id
            )
        
        response = await test_client.get(f"/api/v1/documents?folder_path={folder_path}")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["items"]) >= 2
        assert all(doc["folder_path"] == folder_path for doc in data["items"])


@pytest.mark.integration
class TestSearchEndpoints:
    """Test search API endpoints."""
    
    @pytest.mark.asyncio
    async def test_search_documents_success(self, test_client: AsyncClient, test_db):
        """Test successful document search."""
        # Create searchable documents
        user = await UserFactory.create_and_save_user(test_db)
        await DocumentFactory.create_and_save_document(
            test_db,
            title="Python Programming Guide",
            content="# Python Programming\n\nLearn Python programming language.",
            author_id=user.id
        )
        
        response = await test_client.get("/api/v1/search?q=python")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "results" in data
        assert "total" in data
        assert "query_time_ms" in data
    
    @pytest.mark.asyncio
    async def test_search_empty_query(self, test_client: AsyncClient):
        """Test search with empty query."""
        response = await test_client.get("/api/v1/search?q=")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["results"] == []
        assert data["total"] == 0
    
    @pytest.mark.asyncio
    async def test_autocomplete_tags_success(self, test_client: AsyncClient, test_db):
        """Test tag autocomplete functionality."""
        # Create tags
        from tests.conftest import TagFactory
        await TagFactory.create_and_save_tag(test_db, name="python", usage_count=10)
        await TagFactory.create_and_save_tag(test_db, name="pytorch", usage_count=5)
        
        response = await test_client.get("/api/v1/search/autocomplete?q=py")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "suggestions" in data
        assert "total_count" in data
        assert "query_time_ms" in data
        
        # Should return tags starting with "py"
        suggestions = data["suggestions"]
        assert len(suggestions) >= 2
        assert all("py" in suggestion["name"].lower() for suggestion in suggestions)


@pytest.mark.integration
class TestFileEndpoints:
    """Test file upload and management endpoints."""
    
    @pytest.mark.asyncio
    async def test_upload_file_success(self, test_client: AsyncClient):
        """Test successful file upload."""
        # Create test file content
        file_content = b"Test file content"
        files = {"file": ("test.txt", file_content, "text/plain")}
        data = {"folder_path": "/uploads/"}
        
        response = await test_client.post("/api/v1/files/upload", files=files, data=data)
        
        assert response.status_code == status.HTTP_201_CREATED
        response_data = response.json()
        assert "file_id" in response_data
        assert "filename" in response_data
        assert "file_path" in response_data
        assert response_data["mime_type"] == "text/plain"
    
    @pytest.mark.asyncio
    async def test_upload_file_invalid_type(self, test_client: AsyncClient):
        """Test file upload with invalid file type."""
        # Create executable file (should be rejected)
        file_content = b"#!/bin/bash\necho 'malicious script'"
        files = {"file": ("malicious.sh", file_content, "application/x-sh")}
        data = {"folder_path": "/uploads/"}
        
        response = await test_client.post("/api/v1/files/upload", files=files, data=data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert "not allowed" in data["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_upload_file_too_large(self, test_client: AsyncClient):
        """Test file upload with file too large."""
        # Create large file content (over limit)
        large_content = b"x" * (100 * 1024 * 1024 + 1)  # 100MB + 1 byte
        files = {"file": ("large.txt", large_content, "text/plain")}
        data = {"folder_path": "/uploads/"}
        
        response = await test_client.post("/api/v1/files/upload", files=files, data=data)
        
        assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE


@pytest.mark.integration
class TestTagEndpoints:
    """Test tag management endpoints."""
    
    @pytest.mark.asyncio
    async def test_create_tag_success(self, test_client: AsyncClient):
        """Test successful tag creation."""
        tag_data = {
            "name": "new-tag",
            "description": "A new tag for testing",
            "color": "#007acc"
        }
        
        response = await test_client.post("/api/v1/tags", json=tag_data)
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == tag_data["name"]
        assert data["description"] == tag_data["description"]
        assert data["color"] == tag_data["color"]
        assert data["usage_count"] == 0
    
    @pytest.mark.asyncio
    async def test_get_tags_list(self, test_client: AsyncClient, test_db):
        """Test getting list of tags."""
        # Create test tags
        from tests.conftest import TagFactory
        for i in range(3):
            await TagFactory.create_and_save_tag(
                test_db,
                name=f"tag-{i}",
                usage_count=i * 2
            )
        
        response = await test_client.get("/api/v1/tags")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) >= 3
        assert all("name" in tag for tag in data)
        assert all("usage_count" in tag for tag in data)
    
    @pytest.mark.asyncio
    async def test_update_tag_success(self, test_client: AsyncClient, test_tag):
        """Test successful tag update."""
        update_data = {
            "name": "updated-tag",
            "description": "Updated description"
        }
        
        response = await test_client.put(f"/api/v1/tags/{test_tag.id}", json=update_data)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == update_data["name"]
        assert data["description"] == update_data["description"]
    
    @pytest.mark.asyncio
    async def test_delete_tag_success(self, test_client: AsyncClient, test_tag):
        """Test successful tag deletion."""
        response = await test_client.delete(f"/api/v1/tags/{test_tag.id}")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True


@pytest.mark.integration
class TestPermissionEndpoints:
    """Test permission management endpoints (admin only)."""
    
    @pytest.mark.asyncio
    async def test_create_permission_group_success(self, test_client: AsyncClient, test_admin_user, mock_current_admin_user):
        """Test successful permission group creation by admin."""
        # Override current user to admin
        from app.main import app
        from app.core.auth import get_current_user
        app.dependency_overrides[get_current_user] = mock_current_admin_user
        
        group_data = {
            "name": "test-group",
            "description": "Test permission group"
        }
        
        response = await test_client.post("/api/v1/admin/permission-groups", json=group_data)
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == group_data["name"]
        assert data["description"] == group_data["description"]
    
    @pytest.mark.asyncio
    async def test_create_permission_group_non_admin(self, test_client: AsyncClient):
        """Test permission group creation by non-admin user (should fail)."""
        group_data = {
            "name": "test-group",
            "description": "Test permission group"
        }
        
        response = await test_client.post("/api/v1/admin/permission-groups", json=group_data)
        
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.integration
class TestHealthEndpoints:
    """Test health check endpoints."""
    
    @pytest.mark.asyncio
    async def test_health_check_success(self, test_client: AsyncClient):
        """Test health check endpoint."""
        response = await test_client.get("/api/v1/health")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "version" in data
    
    @pytest.mark.asyncio
    async def test_health_check_detailed(self, test_client: AsyncClient):
        """Test detailed health check endpoint."""
        response = await test_client.get("/api/v1/health/detailed")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "healthy"
        assert "database" in data["checks"]
        assert "redis" in data["checks"]
        assert "timestamp" in data