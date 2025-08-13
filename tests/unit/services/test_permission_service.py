"""
Unit tests for permission service.
"""
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.permission import PermissionService
from app.models.user import User, UserRole
from app.models.permission import PermissionGroup, Permission, PermissionAction, PermissionEffect
from app.core.exceptions import NotFoundError, ValidationError, PermissionDeniedError
from tests.conftest import UserFactory


@pytest.mark.unit
class TestPermissionService:
    """Test cases for PermissionService."""
    
    @pytest.fixture
    def permission_service(self, mock_db):
        """Create permission service with mocked database."""
        return PermissionService(mock_db)
    
    @pytest.fixture
    def mock_user(self):
        """Create a mock normal user."""
        return UserFactory.create_user(role=UserRole.NORMAL)
    
    @pytest.fixture
    def mock_admin_user(self):
        """Create a mock admin user."""
        return UserFactory.create_user(role=UserRole.ADMIN)
    
    @pytest.fixture
    def mock_permission_group(self):
        """Create a mock permission group."""
        group = MagicMock(spec=PermissionGroup)
        group.id = uuid.uuid4()
        group.name = "editors"
        group.description = "Content editors group"
        return group
    
    @pytest.fixture
    def mock_permission(self, mock_permission_group):
        """Create a mock permission."""
        permission = MagicMock(spec=Permission)
        permission.id = uuid.uuid4()
        permission.group_id = mock_permission_group.id
        permission.resource_pattern = "/docs/*"
        permission.action = PermissionAction.EDIT_PAGES
        permission.effect = PermissionEffect.ALLOW
        return permission
    
    @pytest.mark.asyncio
    async def test_check_permission_admin_user(self, permission_service, mock_admin_user):
        """Test permission check for admin user (should always return True)."""
        result = await permission_service.check_permission(
            mock_admin_user, "/any/resource", PermissionAction.EDIT_PAGES
        )
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_check_permission_normal_user_allowed(self, permission_service, mock_db, mock_user, mock_permission):
        """Test permission check for normal user with allowed permission."""
        # Mock user groups and permissions
        mock_db.execute.return_value.scalars.return_value.all.side_effect = [
            [mock_permission.group_id],  # User groups
            [mock_permission]  # Matching permissions
        ]
        
        result = await permission_service.check_permission(
            mock_user, "/docs/test", PermissionAction.EDIT_PAGES
        )
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_check_permission_normal_user_denied(self, permission_service, mock_db, mock_user):
        """Test permission check for normal user with no matching permissions."""
        # Mock no user groups
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        
        result = await permission_service.check_permission(
            mock_user, "/restricted/resource", PermissionAction.EDIT_PAGES
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_check_permission_explicit_deny(self, permission_service, mock_db, mock_user, mock_permission):
        """Test permission check with explicit deny rule."""
        # Create deny permission
        mock_permission.effect = PermissionEffect.DENY
        
        mock_db.execute.return_value.scalars.return_value.all.side_effect = [
            [mock_permission.group_id],  # User groups
            [mock_permission]  # Matching permissions (deny)
        ]
        
        result = await permission_service.check_permission(
            mock_user, "/docs/test", PermissionAction.EDIT_PAGES
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_create_permission_group_success(self, permission_service, mock_db, mock_admin_user):
        """Test successful permission group creation."""
        group_data = MagicMock()
        group_data.name = "new-group"
        group_data.description = "New permission group"
        
        # Mock no existing group
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        
        result = await permission_service.create_permission_group(group_data, mock_admin_user)
        
        mock_db.add.assert_called()
        mock_db.commit.assert_called()
        mock_db.refresh.assert_called()
    
    @pytest.mark.asyncio
    async def test_create_permission_group_non_admin(self, permission_service, mock_user):
        """Test permission group creation by non-admin user."""
        group_data = MagicMock()
        
        with pytest.raises(PermissionDeniedError, match="Admin privileges required"):
            await permission_service.create_permission_group(group_data, mock_user)
    
    @pytest.mark.asyncio
    async def test_create_permission_group_duplicate_name(self, permission_service, mock_db, mock_admin_user, mock_permission_group):
        """Test permission group creation with duplicate name."""
        group_data = MagicMock()
        group_data.name = "existing-group"
        
        # Mock existing group
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_permission_group
        
        with pytest.raises(ValidationError, match="Permission group 'existing-group' already exists"):
            await permission_service.create_permission_group(group_data, mock_admin_user)
    
    @pytest.mark.asyncio
    async def test_add_permission_to_group_success(self, permission_service, mock_db, mock_admin_user, mock_permission_group):
        """Test successfully adding permission to group."""
        permission_data = MagicMock()
        permission_data.resource_pattern = "/docs/*"
        permission_data.action = PermissionAction.READ_PAGES
        permission_data.effect = PermissionEffect.ALLOW
        
        # Mock existing group
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_permission_group
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        
        result = await permission_service.add_permission_to_group(
            mock_permission_group.id, permission_data, mock_admin_user
        )
        
        mock_db.add.assert_called()
        mock_db.commit.assert_called()
        mock_db.refresh.assert_called()
    
    @pytest.mark.asyncio
    async def test_add_permission_to_group_not_found(self, permission_service, mock_db, mock_admin_user):
        """Test adding permission to non-existent group."""
        group_id = uuid.uuid4()
        permission_data = MagicMock()
        
        # Mock no existing group
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        
        with pytest.raises(NotFoundError, match=f"Permission group with ID {group_id} not found"):
            await permission_service.add_permission_to_group(group_id, permission_data, mock_admin_user)
    
    @pytest.mark.asyncio
    async def test_assign_user_to_group_success(self, permission_service, mock_db, mock_admin_user, mock_user, mock_permission_group):
        """Test successfully assigning user to group."""
        # Mock existing user and group
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [
            mock_user,  # User exists
            mock_permission_group,  # Group exists
            None  # No existing assignment
        ]
        mock_db.commit = AsyncMock()
        
        result = await permission_service.assign_user_to_group(
            mock_user.id, mock_permission_group.id, mock_admin_user
        )
        
        assert result.success is True
        mock_db.add.assert_called()
        mock_db.commit.assert_called()
    
    @pytest.mark.asyncio
    async def test_assign_user_to_group_user_not_found(self, permission_service, mock_db, mock_admin_user):
        """Test assigning non-existent user to group."""
        user_id = uuid.uuid4()
        group_id = uuid.uuid4()
        
        # Mock no existing user
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        
        with pytest.raises(NotFoundError, match=f"User with ID {user_id} not found"):
            await permission_service.assign_user_to_group(user_id, group_id, mock_admin_user)
    
    @pytest.mark.asyncio
    async def test_assign_user_to_group_already_assigned(self, permission_service, mock_db, mock_admin_user, mock_user, mock_permission_group):
        """Test assigning user to group when already assigned."""
        # Mock existing user, group, and assignment
        mock_assignment = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [
            mock_user,  # User exists
            mock_permission_group,  # Group exists
            mock_assignment  # Existing assignment
        ]
        
        with pytest.raises(ValidationError, match="User is already assigned to this group"):
            await permission_service.assign_user_to_group(
                mock_user.id, mock_permission_group.id, mock_admin_user
            )
    
    @pytest.mark.asyncio
    async def test_remove_user_from_group_success(self, permission_service, mock_db, mock_admin_user):
        """Test successfully removing user from group."""
        user_id = uuid.uuid4()
        group_id = uuid.uuid4()
        
        # Mock existing assignment
        mock_assignment = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_assignment
        mock_db.delete = AsyncMock()
        mock_db.commit = AsyncMock()
        
        result = await permission_service.remove_user_from_group(user_id, group_id, mock_admin_user)
        
        assert result.success is True
        mock_db.delete.assert_called_once()
        mock_db.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_remove_user_from_group_not_assigned(self, permission_service, mock_db, mock_admin_user):
        """Test removing user from group when not assigned."""
        user_id = uuid.uuid4()
        group_id = uuid.uuid4()
        
        # Mock no existing assignment
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        
        with pytest.raises(NotFoundError, match="User is not assigned to this group"):
            await permission_service.remove_user_from_group(user_id, group_id, mock_admin_user)
    
    @pytest.mark.asyncio
    async def test_get_user_permissions_success(self, permission_service, mock_db, mock_user, mock_permission):
        """Test getting user permissions."""
        # Mock user groups and permissions
        mock_db.execute.return_value.scalars.return_value.all.side_effect = [
            [mock_permission.group_id],  # User groups
            [mock_permission]  # Group permissions
        ]
        
        result = await permission_service.get_user_permissions(mock_user.id)
        
        assert len(result) == 1
        assert result[0] == mock_permission
    
    @pytest.mark.asyncio
    async def test_get_user_groups_success(self, permission_service, mock_db, mock_user, mock_permission_group):
        """Test getting user groups."""
        # Mock user groups
        mock_db.execute.return_value.scalars.return_value.all.return_value = [mock_permission_group]
        
        result = await permission_service.get_user_groups(mock_user.id)
        
        assert len(result) == 1
        assert result[0] == mock_permission_group
    
    @pytest.mark.asyncio
    async def test_get_group_permissions_success(self, permission_service, mock_db, mock_permission_group, mock_permission):
        """Test getting group permissions."""
        # Mock group permissions
        mock_db.execute.return_value.scalars.return_value.all.return_value = [mock_permission]
        
        result = await permission_service.get_group_permissions(mock_permission_group.id)
        
        assert len(result) == 1
        assert result[0] == mock_permission
    
    def test_match_resource_pattern_exact_match(self, permission_service):
        """Test resource pattern matching with exact match."""
        pattern = "/docs/api"
        resource = "/docs/api"
        
        result = permission_service._match_resource_pattern(pattern, resource)
        
        assert result is True
    
    def test_match_resource_pattern_wildcard_match(self, permission_service):
        """Test resource pattern matching with wildcard."""
        pattern = "/docs/*"
        resource = "/docs/api/users"
        
        result = permission_service._match_resource_pattern(pattern, resource)
        
        assert result is True
    
    def test_match_resource_pattern_no_match(self, permission_service):
        """Test resource pattern matching with no match."""
        pattern = "/docs/*"
        resource = "/admin/users"
        
        result = permission_service._match_resource_pattern(pattern, resource)
        
        assert result is False
    
    def test_match_resource_pattern_recursive_wildcard(self, permission_service):
        """Test resource pattern matching with recursive wildcard."""
        pattern = "/docs/**"
        resource = "/docs/api/v1/users"
        
        result = permission_service._match_resource_pattern(pattern, resource)
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_evaluate_permissions_allow_wins(self, permission_service, mock_user):
        """Test permission evaluation where allow rule wins over default deny."""
        permissions = [
            MagicMock(
                resource_pattern="/docs/*",
                action=PermissionAction.READ_PAGES,
                effect=PermissionEffect.ALLOW
            )
        ]
        
        result = permission_service._evaluate_permissions(
            permissions, "/docs/test", PermissionAction.READ_PAGES
        )
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_evaluate_permissions_deny_wins(self, permission_service, mock_user):
        """Test permission evaluation where deny rule wins."""
        permissions = [
            MagicMock(
                resource_pattern="/docs/*",
                action=PermissionAction.READ_PAGES,
                effect=PermissionEffect.ALLOW
            ),
            MagicMock(
                resource_pattern="/docs/secret/*",
                action=PermissionAction.READ_PAGES,
                effect=PermissionEffect.DENY
            )
        ]
        
        result = permission_service._evaluate_permissions(
            permissions, "/docs/secret/file", PermissionAction.READ_PAGES
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_evaluate_permissions_no_match(self, permission_service, mock_user):
        """Test permission evaluation with no matching rules."""
        permissions = [
            MagicMock(
                resource_pattern="/docs/*",
                action=PermissionAction.READ_PAGES,
                effect=PermissionEffect.ALLOW
            )
        ]
        
        result = permission_service._evaluate_permissions(
            permissions, "/admin/users", PermissionAction.READ_PAGES
        )
        
        assert result is False  # Default deny
    
    @pytest.mark.asyncio
    async def test_delete_permission_group_success(self, permission_service, mock_db, mock_admin_user, mock_permission_group):
        """Test successful permission group deletion."""
        # Mock existing group with no users
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_permission_group
        mock_db.execute.return_value.scalar.return_value = 0  # No users in group
        mock_db.delete = AsyncMock()
        mock_db.commit = AsyncMock()
        
        result = await permission_service.delete_permission_group(mock_permission_group.id, mock_admin_user)
        
        assert result.success is True
        mock_db.delete.assert_called_once()
        mock_db.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_delete_permission_group_has_users(self, permission_service, mock_db, mock_admin_user, mock_permission_group):
        """Test permission group deletion when group has users."""
        # Mock existing group with users
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_permission_group
        mock_db.execute.return_value.scalar.return_value = 3  # 3 users in group
        
        with pytest.raises(ValidationError, match="Cannot delete permission group 'editors' as it has 3 assigned users"):
            await permission_service.delete_permission_group(mock_permission_group.id, mock_admin_user)
    
    @pytest.mark.asyncio
    async def test_update_permission_group_success(self, permission_service, mock_db, mock_admin_user, mock_permission_group):
        """Test successful permission group update."""
        update_data = MagicMock()
        update_data.name = "updated-group"
        update_data.description = "Updated description"
        
        # Mock existing group and no name conflict
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [
            mock_permission_group,  # Existing group
            None  # No name conflict
        ]
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        
        result = await permission_service.update_permission_group(
            mock_permission_group.id, update_data, mock_admin_user
        )
        
        assert mock_permission_group.name == "updated-group"
        assert mock_permission_group.description == "Updated description"
        mock_db.commit.assert_called()
        mock_db.refresh.assert_called()