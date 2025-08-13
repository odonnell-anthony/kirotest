"""
Unit tests for authentication service.
"""
import pytest
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from jose import jwt

from app.services.auth import AuthenticationService, AuthenticationError, AuthorizationError
from app.models.user import User, UserRole
from app.core.config import settings
from tests.conftest import UserFactory


@pytest.mark.unit
class TestAuthenticationService:
    """Test cases for AuthenticationService."""
    
    @pytest.fixture
    def auth_service(self, mock_db):
        """Create auth service with mocked dependencies."""
        return AuthenticationService(mock_db)
    
    @pytest.fixture
    def mock_user(self):
        """Create a mock user."""
        return UserFactory.create_user(
            username="testuser",
            email="test@example.com",
            role=UserRole.NORMAL
        )
    
    def test_hash_password(self):
        """Test password hashing."""
        password = "test_password_123"
        hashed = AuthenticationService.hash_password(password)
        
        assert hashed != password
        assert hashed.startswith("$2b$")
        assert len(hashed) > 50
    
    def test_verify_password_correct(self):
        """Test password verification with correct password."""
        password = "test_password_123"
        hashed = AuthenticationService.hash_password(password)
        
        assert AuthenticationService.verify_password(password, hashed) is True
    
    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password."""
        password = "test_password_123"
        wrong_password = "wrong_password"
        hashed = AuthenticationService.hash_password(password)
        
        assert AuthenticationService.verify_password(wrong_password, hashed) is False
    
    def test_create_access_token(self):
        """Test JWT access token creation."""
        user_data = {"sub": str(uuid.uuid4()), "username": "testuser", "role": "normal"}
        token = AuthenticationService.create_access_token(user_data)
        
        assert isinstance(token, str)
        assert len(token) > 100  # JWT tokens are long
        
        # Decode and verify token
        decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert decoded["sub"] == user_data["sub"]
        assert decoded["username"] == user_data["username"]
        assert decoded["role"] == user_data["role"]
        assert "exp" in decoded
        assert "iat" in decoded
    
    def test_create_refresh_token(self):
        """Test JWT refresh token creation."""
        user_data = {"sub": str(uuid.uuid4()), "username": "testuser"}
        token = AuthenticationService.create_refresh_token(user_data)
        
        assert isinstance(token, str)
        assert len(token) > 100
        
        # Decode and verify token
        decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert decoded["sub"] == user_data["sub"]
        assert decoded["username"] == user_data["username"]
        assert decoded["type"] == "refresh"
    
    @pytest.mark.asyncio
    async def test_authenticate_user_success(self, auth_service, mock_db, mock_user):
        """Test successful user authentication."""
        # Mock database query
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_user
        
        # Mock password verification
        with patch.object(AuthenticationService, 'verify_password', return_value=True):
            result = await auth_service.authenticate_user("testuser", "password")
        
        assert result == mock_user
        mock_db.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_authenticate_user_not_found(self, auth_service, mock_db):
        """Test authentication with non-existent user."""
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        
        with pytest.raises(AuthenticationError, match="Invalid username or password"):
            await auth_service.authenticate_user("nonexistent", "password")
    
    @pytest.mark.asyncio
    async def test_authenticate_user_wrong_password(self, auth_service, mock_db, mock_user):
        """Test authentication with wrong password."""
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_user
        
        with patch.object(AuthenticationService, 'verify_password', return_value=False):
            with pytest.raises(AuthenticationError, match="Invalid username or password"):
                await auth_service.authenticate_user("testuser", "wrong_password")
    
    @pytest.mark.asyncio
    async def test_authenticate_user_inactive(self, auth_service, mock_db):
        """Test authentication with inactive user."""
        inactive_user = UserFactory.create_user(is_active=False)
        mock_db.execute.return_value.scalar_one_or_none.return_value = inactive_user
        
        with patch.object(AuthenticationService, 'verify_password', return_value=True):
            with pytest.raises(AuthenticationError, match="User account is disabled"):
                await auth_service.authenticate_user("testuser", "password")
    
    @pytest.mark.asyncio
    async def test_get_user_by_token_success(self, auth_service, mock_db, mock_user):
        """Test getting user by valid token."""
        # Create token
        token_data = {"sub": str(mock_user.id), "username": mock_user.username}
        token = AuthenticationService.create_access_token(token_data)
        
        # Mock database query
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_user
        
        result = await auth_service.get_user_by_token(token)
        
        assert result == mock_user
        mock_db.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_user_by_token_invalid(self, auth_service):
        """Test getting user by invalid token."""
        invalid_token = "invalid.token.here"
        
        with pytest.raises(AuthenticationError, match="Invalid token"):
            await auth_service.get_user_by_token(invalid_token)
    
    @pytest.mark.asyncio
    async def test_get_user_by_token_expired(self, auth_service):
        """Test getting user by expired token."""
        # Create expired token
        expired_data = {
            "sub": str(uuid.uuid4()),
            "username": "testuser",
            "exp": datetime.utcnow() - timedelta(hours=1)
        }
        expired_token = jwt.encode(expired_data, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        
        with pytest.raises(AuthenticationError, match="Token has expired"):
            await auth_service.get_user_by_token(expired_token)
    
    @pytest.mark.asyncio
    async def test_get_user_by_token_user_not_found(self, auth_service, mock_db):
        """Test getting user by token when user doesn't exist in database."""
        # Create valid token for non-existent user
        token_data = {"sub": str(uuid.uuid4()), "username": "nonexistent"}
        token = AuthenticationService.create_access_token(token_data)
        
        # Mock database query returning None
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        
        with pytest.raises(AuthenticationError, match="User not found"):
            await auth_service.get_user_by_token(token)
    
    @pytest.mark.asyncio
    @patch('app.services.auth.get_redis')
    async def test_blacklist_token_success(self, mock_get_redis, auth_service):
        """Test successful token blacklisting."""
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        token_data = {"sub": str(uuid.uuid4()), "jti": str(uuid.uuid4())}
        token = AuthenticationService.create_access_token(token_data)
        
        await auth_service.blacklist_token(token)
        
        mock_redis.setex.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.services.auth.get_redis')
    async def test_is_token_blacklisted_true(self, mock_get_redis, auth_service):
        """Test checking if token is blacklisted (true case)."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "blacklisted"
        mock_get_redis.return_value = mock_redis
        
        token_data = {"sub": str(uuid.uuid4()), "jti": str(uuid.uuid4())}
        token = AuthenticationService.create_access_token(token_data)
        
        result = await auth_service.is_token_blacklisted(token)
        
        assert result is True
        mock_redis.get.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.services.auth.get_redis')
    async def test_is_token_blacklisted_false(self, mock_get_redis, auth_service):
        """Test checking if token is blacklisted (false case)."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis
        
        token_data = {"sub": str(uuid.uuid4()), "jti": str(uuid.uuid4())}
        token = AuthenticationService.create_access_token(token_data)
        
        result = await auth_service.is_token_blacklisted(token)
        
        assert result is False
        mock_redis.get.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_refresh_access_token_success(self, auth_service, mock_db, mock_user):
        """Test successful access token refresh."""
        # Create refresh token
        token_data = {"sub": str(mock_user.id), "username": mock_user.username, "type": "refresh"}
        refresh_token = AuthenticationService.create_refresh_token(token_data)
        
        # Mock database query
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_user
        
        new_access_token = await auth_service.refresh_access_token(refresh_token)
        
        assert isinstance(new_access_token, str)
        assert len(new_access_token) > 100
        
        # Verify new token contains correct data
        decoded = jwt.decode(new_access_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert decoded["sub"] == str(mock_user.id)
        assert decoded["username"] == mock_user.username
    
    @pytest.mark.asyncio
    async def test_refresh_access_token_invalid_type(self, auth_service):
        """Test refresh token with wrong type."""
        # Create access token instead of refresh token
        token_data = {"sub": str(uuid.uuid4()), "username": "testuser"}
        access_token = AuthenticationService.create_access_token(token_data)
        
        with pytest.raises(AuthenticationError, match="Invalid refresh token"):
            await auth_service.refresh_access_token(access_token)
    
    @pytest.mark.asyncio
    async def test_update_last_login(self, auth_service, mock_db, mock_user):
        """Test updating user's last login timestamp."""
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        
        await auth_service.update_last_login(mock_user)
        
        assert mock_user.last_login_at is not None
        assert isinstance(mock_user.last_login_at, datetime)
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_session_success(self, auth_service, mock_user):
        """Test successful session creation."""
        with patch('app.services.auth.get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_get_redis.return_value = mock_redis
            
            session_data = await auth_service.create_session(mock_user, "127.0.0.1", "test-agent")
            
            assert "session_id" in session_data
            assert "access_token" in session_data
            assert "refresh_token" in session_data
            assert session_data["user_id"] == str(mock_user.id)
            
            mock_redis.setex.assert_called()
    
    @pytest.mark.asyncio
    async def test_validate_session_success(self, auth_service):
        """Test successful session validation."""
        session_id = str(uuid.uuid4())
        
        with patch('app.services.auth.get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.get.return_value = '{"user_id": "test-user-id", "ip_address": "127.0.0.1"}'
            mock_get_redis.return_value = mock_redis
            
            result = await auth_service.validate_session(session_id)
            
            assert result is not None
            assert result["user_id"] == "test-user-id"
            mock_redis.get.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_validate_session_not_found(self, auth_service):
        """Test session validation when session doesn't exist."""
        session_id = str(uuid.uuid4())
        
        with patch('app.services.auth.get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.get.return_value = None
            mock_get_redis.return_value = mock_redis
            
            result = await auth_service.validate_session(session_id)
            
            assert result is None
            mock_redis.get.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_invalidate_session_success(self, auth_service):
        """Test successful session invalidation."""
        session_id = str(uuid.uuid4())
        
        with patch('app.services.auth.get_redis') as mock_get_redis:
            mock_redis = AsyncMock()
            mock_get_redis.return_value = mock_redis
            
            await auth_service.invalidate_session(session_id)
            
            mock_redis.delete.assert_called_once_with(f"session:{session_id}")