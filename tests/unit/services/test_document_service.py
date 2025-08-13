"""
Unit tests for document service.
"""
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.document import DocumentService
from app.models.document import Document, DocumentStatus
from app.models.user import User, UserRole
from app.models.folder import Folder
from app.core.exceptions import NotFoundError, ValidationError, DuplicateError
from tests.conftest import UserFactory, DocumentFactory


@pytest.mark.unit
class TestDocumentService:
    """Test cases for DocumentService."""
    
    @pytest.fixture
    def document_service(self, mock_db):
        """Create document service with mocked database."""
        return DocumentService(mock_db)
    
    @pytest.fixture
    def mock_user(self):
        """Create a mock user."""
        return UserFactory.create_user()
    
    @pytest.fixture
    def mock_document(self, mock_user):
        """Create a mock document."""
        return DocumentFactory.create_document(author_id=mock_user.id)
    
    @pytest.fixture
    def mock_folder(self, mock_user):
        """Create a mock folder."""
        folder = MagicMock(spec=Folder)
        folder.id = uuid.uuid4()
        folder.name = "test-folder"
        folder.path = "/test-folder/"
        folder.created_by = mock_user.id
        return folder
    
    @pytest.mark.asyncio
    async def test_create_document_success(self, document_service, mock_db, mock_user):
        """Test successful document creation."""
        # Mock document data
        doc_data = MagicMock()
        doc_data.title = "Test Document"
        doc_data.content = "# Test Content"
        doc_data.folder_path = "/test/"
        doc_data.tags = ["python", "testing"]
        doc_data.status = DocumentStatus.PUBLISHED
        
        # Mock database responses
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [
            None,  # No existing document with same title
            None,  # No existing folder (will be created)
        ]
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        
        # Mock folder creation
        with patch.object(document_service, '_ensure_folder_exists', return_value=None):
            with patch.object(document_service, '_generate_slug', return_value="test-document"):
                with patch.object(document_service, '_process_tags', return_value=[]):
                    result = await document_service.create_document(doc_data, mock_user)
        
        mock_db.add.assert_called()
        mock_db.commit.assert_called()
        mock_db.refresh.assert_called()
    
    @pytest.mark.asyncio
    async def test_create_document_duplicate_title(self, document_service, mock_db, mock_user, mock_document):
        """Test document creation with duplicate title in same folder."""
        doc_data = MagicMock()
        doc_data.title = "Test Document"
        doc_data.folder_path = "/test/"
        
        # Mock existing document with same title
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_document
        
        with pytest.raises(DuplicateError, match="Document with title 'Test Document' already exists"):
            await document_service.create_document(doc_data, mock_user)
    
    @pytest.mark.asyncio
    async def test_get_document_success(self, document_service, mock_db, mock_document):
        """Test successful document retrieval."""
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_document
        
        result = await document_service.get_document(mock_document.id)
        
        assert result == mock_document
        mock_db.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_document_not_found(self, document_service, mock_db):
        """Test document retrieval when document doesn't exist."""
        doc_id = uuid.uuid4()
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        
        with pytest.raises(NotFoundError, match=f"Document with ID {doc_id} not found"):
            await document_service.get_document(doc_id)
    
    @pytest.mark.asyncio
    async def test_update_document_success(self, document_service, mock_db, mock_user, mock_document):
        """Test successful document update."""
        update_data = MagicMock()
        update_data.title = "Updated Title"
        update_data.content = "# Updated Content"
        update_data.tags = ["python", "updated"]
        
        # Mock database responses
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [
            mock_document,  # Get existing document
            None,  # No title conflict
        ]
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        
        with patch.object(document_service, '_create_revision', return_value=None):
            with patch.object(document_service, '_process_tags', return_value=[]):
                result = await document_service.update_document(mock_document.id, update_data, mock_user)
        
        assert mock_document.title == "Updated Title"
        assert mock_document.content == "# Updated Content"
        mock_db.commit.assert_called()
        mock_db.refresh.assert_called()
    
    @pytest.mark.asyncio
    async def test_update_document_not_found(self, document_service, mock_db, mock_user):
        """Test document update when document doesn't exist."""
        doc_id = uuid.uuid4()
        update_data = MagicMock()
        
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        
        with pytest.raises(NotFoundError, match=f"Document with ID {doc_id} not found"):
            await document_service.update_document(doc_id, update_data, mock_user)
    
    @pytest.mark.asyncio
    async def test_delete_document_success(self, document_service, mock_db, mock_user, mock_document):
        """Test successful document deletion."""
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_document
        mock_db.delete = AsyncMock()
        mock_db.commit = AsyncMock()
        
        result = await document_service.delete_document(mock_document.id, mock_user)
        
        assert result.success is True
        mock_db.delete.assert_called_once()
        mock_db.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_delete_document_not_found(self, document_service, mock_db, mock_user):
        """Test document deletion when document doesn't exist."""
        doc_id = uuid.uuid4()
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        
        with pytest.raises(NotFoundError, match=f"Document with ID {doc_id} not found"):
            await document_service.delete_document(doc_id, mock_user)
    
    @pytest.mark.asyncio
    async def test_move_document_success(self, document_service, mock_db, mock_user, mock_document):
        """Test successful document move."""
        new_path = "/new-folder/"
        
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_document
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        
        with patch.object(document_service, '_ensure_folder_exists', return_value=None):
            result = await document_service.move_document(mock_document.id, new_path, mock_user)
        
        assert mock_document.folder_path == new_path
        mock_db.commit.assert_called()
        mock_db.refresh.assert_called()
    
    @pytest.mark.asyncio
    async def test_get_documents_by_folder_success(self, document_service, mock_db):
        """Test getting documents by folder path."""
        folder_path = "/test/"
        mock_documents = [DocumentFactory.create_document() for _ in range(3)]
        
        mock_db.execute.return_value.scalars.return_value.all.return_value = mock_documents
        
        result = await document_service.get_documents_by_folder(folder_path)
        
        assert len(result) == 3
        assert all(isinstance(doc, Document) for doc in result)
        mock_db.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_documents_by_author_success(self, document_service, mock_db, mock_user):
        """Test getting documents by author."""
        mock_documents = [DocumentFactory.create_document(author_id=mock_user.id) for _ in range(2)]
        
        mock_db.execute.return_value.scalars.return_value.all.return_value = mock_documents
        
        result = await document_service.get_documents_by_author(mock_user.id)
        
        assert len(result) == 2
        assert all(doc.author_id == mock_user.id for doc in result)
        mock_db.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_recent_documents_success(self, document_service, mock_db):
        """Test getting recent documents."""
        mock_documents = [DocumentFactory.create_document() for _ in range(5)]
        
        mock_db.execute.return_value.scalars.return_value.all.return_value = mock_documents
        
        result = await document_service.get_recent_documents(limit=5)
        
        assert len(result) == 5
        mock_db.execute.assert_called_once()
    
    def test_generate_slug_basic(self, document_service):
        """Test basic slug generation."""
        title = "Hello World Document"
        slug = document_service._generate_slug(title)
        
        assert slug == "hello-world-document"
    
    def test_generate_slug_special_characters(self, document_service):
        """Test slug generation with special characters."""
        title = "My Document! @#$%^&*()"
        slug = document_service._generate_slug(title)
        
        assert slug == "my-document"
        assert not any(char in slug for char in "!@#$%^&*()")
    
    def test_generate_slug_multiple_spaces(self, document_service):
        """Test slug generation with multiple spaces."""
        title = "Document   with    multiple     spaces"
        slug = document_service._generate_slug(title)
        
        assert slug == "document-with-multiple-spaces"
    
    def test_generate_slug_empty_title(self, document_service):
        """Test slug generation with empty title."""
        title = ""
        slug = document_service._generate_slug(title)
        
        assert slug == "untitled"
    
    def test_validate_folder_path_valid(self, document_service):
        """Test folder path validation with valid paths."""
        valid_paths = [
            "/",
            "/docs/",
            "/docs/api/",
            "/my-folder/sub-folder/"
        ]
        
        for path in valid_paths:
            # Should not raise exception
            document_service._validate_folder_path(path)
    
    def test_validate_folder_path_invalid(self, document_service):
        """Test folder path validation with invalid paths."""
        invalid_paths = [
            "docs",  # No leading slash
            "/docs",  # No trailing slash
            "/docs with spaces/",  # Spaces not allowed
            "/docs@invalid/",  # Special characters not allowed
            "",  # Empty path
        ]
        
        for path in invalid_paths:
            with pytest.raises(ValidationError):
                document_service._validate_folder_path(path)
    
    def test_sanitize_content_basic(self, document_service):
        """Test basic content sanitization."""
        content = "# Hello World\n\nThis is **bold** text."
        sanitized = document_service._sanitize_content(content)
        
        assert sanitized == content  # Should remain unchanged
    
    def test_sanitize_content_dangerous(self, document_service):
        """Test content sanitization with dangerous content."""
        dangerous_content = "<script>alert('xss')</script><p>Safe content</p>"
        sanitized = document_service._sanitize_content(dangerous_content)
        
        assert "<script>" not in sanitized
        assert "alert('xss')" not in sanitized
        assert "<p>Safe content</p>" in sanitized
    
    @pytest.mark.asyncio
    async def test_ensure_folder_exists_existing(self, document_service, mock_db, mock_user, mock_folder):
        """Test ensuring folder exists when it already exists."""
        folder_path = "/test-folder/"
        
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_folder
        
        result = await document_service._ensure_folder_exists(folder_path, mock_user)
        
        assert result == mock_folder
        mock_db.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_ensure_folder_exists_create_new(self, document_service, mock_db, mock_user):
        """Test ensuring folder exists when it needs to be created."""
        folder_path = "/new-folder/"
        
        # Mock no existing folder
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        
        result = await document_service._ensure_folder_exists(folder_path, mock_user)
        
        mock_db.add.assert_called()
        mock_db.commit.assert_called()
        mock_db.refresh.assert_called()
    
    @pytest.mark.asyncio
    async def test_create_revision_success(self, document_service, mock_db, mock_user, mock_document):
        """Test successful revision creation."""
        change_summary = "Updated content"
        
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        
        # Mock getting next revision number
        mock_db.execute.return_value.scalar.return_value = 1
        
        result = await document_service._create_revision(mock_document, mock_user, change_summary)
        
        mock_db.add.assert_called()
        mock_db.commit.assert_called()
        mock_db.refresh.assert_called()
    
    @pytest.mark.asyncio
    async def test_process_tags_existing_tags(self, document_service, mock_db):
        """Test processing tags with existing tags."""
        tag_names = ["python", "testing"]
        
        # Mock existing tags
        mock_tag1 = MagicMock()
        mock_tag1.name = "python"
        mock_tag2 = MagicMock()
        mock_tag2.name = "testing"
        
        mock_db.execute.return_value.scalars.return_value.all.return_value = [mock_tag1, mock_tag2]
        
        result = await document_service._process_tags(tag_names)
        
        assert len(result) == 2
        assert mock_tag1 in result
        assert mock_tag2 in result
    
    @pytest.mark.asyncio
    async def test_process_tags_create_new(self, document_service, mock_db):
        """Test processing tags with new tags that need to be created."""
        tag_names = ["new-tag"]
        
        # Mock no existing tags
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        
        result = await document_service._process_tags(tag_names)
        
        mock_db.add.assert_called()
        mock_db.commit.assert_called()
        mock_db.refresh.assert_called()
    
    @pytest.mark.asyncio
    async def test_update_search_vector(self, document_service, mock_db, mock_document):
        """Test updating document search vector."""
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()
        
        await document_service._update_search_vector(mock_document)
        
        mock_db.execute.assert_called()
        mock_db.commit.assert_called()