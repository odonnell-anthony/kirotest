"""
Tests for tag management service.
"""
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.tag import TagService
from app.schemas.tag import TagCreate, TagUpdate, TagRenameRequest
from app.models.tag import Tag, DocumentTag
from app.models.user import User, UserRole
from app.core.exceptions import ValidationError, NotFoundError, ConflictError


@pytest.fixture
def mock_db():
    """Mock database session."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_user():
    """Mock user."""
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.username = "testuser"
    user.role = UserRole.NORMAL
    return user


@pytest.fixture
def mock_admin_user():
    """Mock admin user."""
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.username = "admin"
    user.role = UserRole.ADMIN
    return user


@pytest.fixture
def tag_service(mock_db):
    """Tag service instance with mocked database."""
    return TagService(mock_db)


@pytest.fixture
def sample_tag():
    """Sample tag for testing."""
    tag = MagicMock(spec=Tag)
    tag.id = uuid.uuid4()
    tag.name = "python"
    tag.description = "Python programming language"
    tag.color = "#3776ab"
    tag.usage_count = 5
    return tag


class TestTagService:
    """Test cases for TagService."""
    
    @pytest.mark.asyncio
    async def test_create_tag_success(self, tag_service, mock_user, mock_db):
        """Test successful tag creation."""
        # Arrange
        tag_data = TagCreate(
            name="Python",
            description="Python programming language",
            color="#3776ab"
        )
        
        # Mock database responses
        mock_db.execute.return_value.scalar_one_or_none.return_value = None  # No existing tag
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        
        # Mock the created tag
        created_tag = MagicMock(spec=Tag)
        created_tag.id = uuid.uuid4()
        created_tag.name = "python"  # Should be normalized
        created_tag.description = tag_data.description
        created_tag.color = tag_data.color
        created_tag.usage_count = 0
        
        # Act
        result = await tag_service.create_tag(tag_data, mock_user)
        
        # Assert
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_tag_duplicate_name(self, tag_service, mock_user, mock_db, sample_tag):
        """Test tag creation with duplicate name."""
        # Arrange
        tag_data = TagCreate(name="python")
        mock_db.execute.return_value.scalar_one_or_none.return_value = sample_tag
        
        # Act & Assert
        with pytest.raises(ConflictError, match="Tag 'python' already exists"):
            await tag_service.create_tag(tag_data, mock_user)
    
    @pytest.mark.asyncio
    async def test_get_tag_success(self, tag_service, mock_db, sample_tag):
        """Test successful tag retrieval."""
        # Arrange
        mock_db.execute.return_value.scalar_one_or_none.return_value = sample_tag
        
        # Act
        result = await tag_service.get_tag(sample_tag.id)
        
        # Assert
        assert result is not None
        mock_db.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_tag_not_found(self, tag_service, mock_db):
        """Test tag retrieval when tag doesn't exist."""
        # Arrange
        tag_id = uuid.uuid4()
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        
        # Act & Assert
        with pytest.raises(NotFoundError, match=f"Tag with ID {tag_id} not found"):
            await tag_service.get_tag(tag_id)
    
    @pytest.mark.asyncio
    async def test_update_tag_success(self, tag_service, mock_user, mock_db, sample_tag):
        """Test successful tag update."""
        # Arrange
        tag_data = TagUpdate(
            name="python-updated",
            description="Updated description"
        )
        
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [
            sample_tag,  # First call: get existing tag
            None  # Second call: check for name conflicts
        ]
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        
        # Act
        result = await tag_service.update_tag(sample_tag.id, tag_data, mock_user)
        
        # Assert
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_update_tag_name_conflict(self, tag_service, mock_user, mock_db, sample_tag):
        """Test tag update with name conflict."""
        # Arrange
        tag_data = TagUpdate(name="existing-tag")
        
        conflicting_tag = MagicMock(spec=Tag)
        conflicting_tag.id = uuid.uuid4()
        conflicting_tag.name = "existing-tag"
        
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [
            sample_tag,  # First call: get existing tag
            conflicting_tag  # Second call: name conflict
        ]
        
        # Act & Assert
        with pytest.raises(ConflictError, match="Tag 'existing-tag' already exists"):
            await tag_service.update_tag(sample_tag.id, tag_data, mock_user)
    
    @pytest.mark.asyncio
    async def test_rename_tag_success(self, tag_service, mock_user, mock_db, sample_tag):
        """Test successful tag rename."""
        # Arrange
        rename_request = TagRenameRequest(
            old_name="python",
            new_name="python-lang"
        )
        
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [
            sample_tag,  # First call: get old tag
            None  # Second call: check new name conflicts
        ]
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        
        # Act
        result = await tag_service.rename_tag(rename_request, mock_user)
        
        # Assert
        assert sample_tag.name == "python-lang"
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_rename_tag_old_not_found(self, tag_service, mock_user, mock_db):
        """Test tag rename when old tag doesn't exist."""
        # Arrange
        rename_request = TagRenameRequest(
            old_name="nonexistent",
            new_name="new-name"
        )
        
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        
        # Act & Assert
        with pytest.raises(NotFoundError, match="Tag 'nonexistent' not found"):
            await tag_service.rename_tag(rename_request, mock_user)
    
    @pytest.mark.asyncio
    async def test_delete_tag_success(self, tag_service, mock_user, mock_db, sample_tag):
        """Test successful tag deletion."""
        # Arrange
        sample_tag.usage_count = 0  # No usage
        
        mock_db.execute.return_value.scalar_one_or_none.return_value = sample_tag
        mock_db.execute.return_value.fetchall.return_value = []  # No recent documents
        mock_db.delete = AsyncMock()
        mock_db.commit = AsyncMock()
        
        # Act
        result = await tag_service.delete_tag(sample_tag.id, mock_user)
        
        # Assert
        assert result.success is True
        assert result.affected_documents == 0
        mock_db.delete.assert_called_once()
        mock_db.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_delete_tag_in_use_without_force(self, tag_service, mock_user, mock_db, sample_tag):
        """Test tag deletion when tag is in use without force flag."""
        # Arrange
        sample_tag.usage_count = 5  # Tag is in use
        
        mock_db.execute.return_value.scalar_one_or_none.return_value = sample_tag
        mock_db.execute.return_value.fetchall.return_value = [
            ("Document 1",), ("Document 2",)
        ]
        
        # Act & Assert
        with pytest.raises(ValidationError, match="Tag 'python' is used by 5 documents"):
            await tag_service.delete_tag(sample_tag.id, mock_user, force=False)
    
    @pytest.mark.asyncio
    async def test_delete_tag_in_use_with_force(self, tag_service, mock_user, mock_db, sample_tag):
        """Test tag deletion when tag is in use with force flag."""
        # Arrange
        sample_tag.usage_count = 5  # Tag is in use
        
        mock_db.execute.return_value.scalar_one_or_none.return_value = sample_tag
        mock_db.execute.return_value.fetchall.return_value = [
            ("Document 1",), ("Document 2",)
        ]
        mock_db.delete = AsyncMock()
        mock_db.commit = AsyncMock()
        
        # Act
        result = await tag_service.delete_tag(sample_tag.id, mock_user, force=True)
        
        # Assert
        assert result.success is True
        assert result.affected_documents == 5
        mock_db.delete.assert_called_once()
        mock_db.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_autocomplete_tags_success(self, tag_service, mock_db):
        """Test successful tag autocomplete."""
        # Arrange
        mock_db.execute.return_value.fetchall.side_effect = [
            [("python", 10, 0.8), ("pytorch", 5, 0.6)],  # Autocomplete results
            [(2,)]  # Total count
        ]
        
        # Act
        result = await tag_service.autocomplete_tags("py", limit=10)
        
        # Assert
        assert len(result.suggestions) == 2
        assert result.suggestions[0].name == "python"
        assert result.suggestions[0].usage_count == 10
        assert result.total_count == 2
        assert result.query_time_ms >= 0
    
    @pytest.mark.asyncio
    async def test_autocomplete_tags_empty_query(self, tag_service):
        """Test tag autocomplete with empty query."""
        # Act
        result = await tag_service.autocomplete_tags("", limit=10)
        
        # Assert
        assert len(result.suggestions) == 0
        assert result.total_count == 0
        assert result.query_time_ms == 0.0
    
    @pytest.mark.asyncio
    async def test_suggest_tags_success(self, tag_service, mock_db):
        """Test successful tag suggestions."""
        # Arrange
        mock_tags = [
            MagicMock(name="python", usage_count=10),
            MagicMock(name="web", usage_count=8),
            MagicMock(name="api", usage_count=6)
        ]
        mock_db.execute.return_value.scalars.return_value.all.return_value = mock_tags
        
        content = "This is a Python web API tutorial"
        
        # Act
        result = await tag_service.suggest_tags(content, existing_tags=[], limit=5)
        
        # Assert
        assert len(result) > 0
        # Should prioritize tags that appear in content
        python_suggestions = [s for s in result if s.name == "python"]
        assert len(python_suggestions) > 0
        assert python_suggestions[0].similarity_score == 1.0
    
    @pytest.mark.asyncio
    async def test_update_tag_usage_counts(self, tag_service, mock_db):
        """Test updating tag usage counts."""
        # Arrange
        mock_db.execute.side_effect = [
            AsyncMock(),  # UPDATE query
            MagicMock(fetchall=lambda: [("python", 10), ("web", 5)])  # SELECT query
        ]
        mock_db.commit = AsyncMock()
        
        # Act
        result = await tag_service.update_tag_usage_counts()
        
        # Assert
        assert "python" in result
        assert "web" in result
        assert result["python"] == 10
        assert result["web"] == 5
        mock_db.commit.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])