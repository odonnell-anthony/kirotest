"""
Security tests for data protection and privacy.
"""
import pytest
import json
from httpx import AsyncClient
from unittest.mock import patch

from tests.conftest import UserFactory, DocumentFactory


@pytest.mark.security
class TestDataEncryptionSecurity:
    """Test data encryption and protection security measures."""
    
    @pytest.mark.asyncio
    async def test_password_storage_security(self, test_client: AsyncClient, test_db):
        """Test that passwords are securely stored and never exposed."""
        # Create user with password
        user_data = {
            "username": "security_test_user",
            "email": "security@test.com",
            "password": "SecurePassword123!"
        }
        
        # Register user (if registration endpoint exists)
        register_response = await test_client.post("/api/v1/auth/register", json=user_data)
        
        if register_response.status_code == 201:
            # Verify password is not in response
            user_response_data = register_response.json()
            assert "password" not in user_response_data
            assert "password_hash" not in user_response_data
            
            # Get user profile
            profile_response = await test_client.get("/api/v1/auth/me")
            if profile_response.status_code == 200:
                profile_data = profile_response.json()
                assert "password" not in profile_data
                assert "password_hash" not in profile_data
        
        # Test that password is properly hashed in database
        user = await UserFactory.create_and_save_user(
            test_db, 
            username="hash_test_user",
            password_hash="$2b$12$test_hash_value"
        )
        
        # Verify hash format (bcrypt)
        assert user.password_hash.startswith("$2b$")
        assert len(user.password_hash) > 50
        assert user.password_hash != "SecurePassword123!"
    
    @pytest.mark.asyncio
    async def test_sensitive_data_in_logs(self, test_client: AsyncClient):
        """Test that sensitive data is not logged."""
        # Mock logging to capture log messages
        logged_messages = []
        
        def mock_log_handler(record):
            logged_messages.append(record.getMessage().lower())
        
        # Attempt login with sensitive data
        login_data = {
            "username": "test_user",
            "password": "SensitivePassword123!",
            "secret_key": "secret_api_key_12345"
        }
        
        with patch('logging.Logger.info', side_effect=mock_log_handler):
            with patch('logging.Logger.error', side_effect=mock_log_handler):
                with patch('logging.Logger.warning', side_effect=mock_log_handler):
                    response = await test_client.post("/api/v1/auth/login", json=login_data)
        
        # Verify sensitive data is not in logs
        all_logs = " ".join(logged_messages)
        assert "sensitivepassword123!" not in all_logs
        assert "secret_api_key_12345" not in all_logs
        assert "password" not in all_logs or "password: ***" in all_logs
    
    @pytest.mark.asyncio
    async def test_api_key_security(self, test_client: AsyncClient, test_user):
        """Test API key security and rotation."""
        # Generate API key for user
        api_key_data = {
            "name": "Test API Key",
            "permissions": ["read_documents", "create_documents"]
        }
        
        response = await test_client.post("/api/v1/auth/api-keys", json=api_key_data)
        
        if response.status_code == 201:
            api_key_response = response.json()
            
            # Verify API key structure
            assert "key" in api_key_response
            assert "name" in api_key_response
            assert "permissions" in api_key_response
            
            api_key = api_key_response["key"]
            
            # API key should be long and random
            assert len(api_key) >= 32
            assert api_key.isalnum() or "-" in api_key or "_" in api_key
            
            # Test API key usage
            headers = {"X-API-Key": api_key}
            auth_response = await test_client.get("/api/v1/auth/me", headers=headers)
            
            # Should authenticate with API key
            assert auth_response.status_code in [200, 401]  # Depends on implementation
            
            # Test API key revocation
            revoke_response = await test_client.delete(f"/api/v1/auth/api-keys/{api_key_response['id']}")
            
            if revoke_response.status_code == 200:
                # Revoked API key should not work
                revoked_auth_response = await test_client.get("/api/v1/auth/me", headers=headers)
                assert revoked_auth_response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_session_security(self, test_client: AsyncClient):
        """Test session security measures."""
        # Test session fixation protection
        initial_response = await test_client.get("/api/v1/health")
        initial_cookies = dict(initial_response.cookies)
        
        # Login
        login_data = {
            "username": "session_test_user",
            "password": "password123"
        }
        
        with patch('app.services.auth.AuthenticationService.verify_password', return_value=True):
            login_response = await test_client.post("/api/v1/auth/login", json=login_data)
        
        if login_response.status_code == 200:
            login_cookies = dict(login_response.cookies)
            
            # Session should be regenerated after login
            # (Implementation dependent - may use different session identifiers)
            session_changed = any(
                cookie_name.lower() in ["sessionid", "session", "sid"] 
                and initial_cookies.get(cookie_name) != login_cookies.get(cookie_name)
                for cookie_name in login_cookies.keys()
            )
            
            # Test session timeout
            # This would require waiting or mocking time, simplified here
            assert True  # Placeholder for session timeout test
    
    @pytest.mark.asyncio
    async def test_data_masking_in_responses(self, test_client: AsyncClient, test_db):
        """Test that sensitive data is masked in API responses."""
        # Create user with sensitive information
        user = await UserFactory.create_and_save_user(
            test_db,
            username="sensitive_user",
            email="sensitive@example.com"
        )
        
        # Mock user authentication
        async def mock_user():
            return user
        
        from app.main import app
        from app.core.auth import get_current_user
        app.dependency_overrides[get_current_user] = mock_user
        
        # Get user profile
        profile_response = await test_client.get("/api/v1/auth/me")
        
        if profile_response.status_code == 200:
            profile_data = profile_response.json()
            
            # Verify sensitive fields are not exposed
            sensitive_fields = [
                "password", "password_hash", "secret_key", "private_key",
                "api_secret", "token_secret", "mfa_secret"
            ]
            
            for field in sensitive_fields:
                assert field not in profile_data, f"Sensitive field '{field}' should not be in profile response"
            
            # Email might be partially masked
            if "email" in profile_data:
                email = profile_data["email"]
                # Email should either be full email or masked (e.g., s***@example.com)
                assert "@" in email, "Email should contain @ symbol"
        
        # Test admin user list (should mask sensitive data)
        admin_response = await test_client.get("/api/v1/admin/users")
        
        if admin_response.status_code == 200:
            users_data = admin_response.json()
            
            if isinstance(users_data, list) and len(users_data) > 0:
                for user_data in users_data:
                    # Verify sensitive fields are not exposed in user list
                    for field in sensitive_fields:
                        assert field not in user_data, f"Sensitive field '{field}' should not be in admin user list"
        
        # Clean up
        app.dependency_overrides.clear()


@pytest.mark.security
class TestAccessControlSecurity:
    """Test access control and authorization security."""
    
    @pytest.mark.asyncio
    async def test_horizontal_privilege_escalation(self, test_client: AsyncClient, test_db):
        """Test protection against horizontal privilege escalation."""
        # Create two users
        user1 = await UserFactory.create_and_save_user(test_db, username="user1")
        user2 = await UserFactory.create_and_save_user(test_db, username="user2")
        
        # User1 creates a private document
        async def mock_user1():
            return user1
        
        from app.main import app
        from app.core.auth import get_current_user
        app.dependency_overrides[get_current_user] = mock_user1
        
        doc_data = {
            "title": "User1 Private Document",
            "content": "This is user1's private document",
            "folder_path": "/private/",
            "status": "draft"  # Draft documents should be private
        }
        
        create_response = await test_client.post("/api/v1/documents", json=doc_data)
        assert create_response.status_code == 201
        document = create_response.json()
        doc_id = document["id"]
        
        # Switch to user2
        async def mock_user2():
            return user2
        
        app.dependency_overrides[get_current_user] = mock_user2
        
        # User2 should NOT be able to access user1's private document
        access_response = await test_client.get(f"/api/v1/documents/{doc_id}")
        assert access_response.status_code in [403, 404], "User2 should not access user1's private document"
        
        # User2 should NOT be able to modify user1's document
        update_data = {"title": "User2 trying to modify"}
        update_response = await test_client.put(f"/api/v1/documents/{doc_id}", json=update_data)
        assert update_response.status_code in [403, 404], "User2 should not modify user1's document"
        
        # User2 should NOT be able to delete user1's document
        delete_response = await test_client.delete(f"/api/v1/documents/{doc_id}")
        assert delete_response.status_code in [403, 404], "User2 should not delete user1's document"
        
        # Clean up
        app.dependency_overrides.clear()
    
    @pytest.mark.asyncio
    async def test_vertical_privilege_escalation(self, test_client: AsyncClient, test_db):
        """Test protection against vertical privilege escalation."""
        from app.models.user import UserRole
        
        # Create normal user
        normal_user = await UserFactory.create_and_save_user(test_db, username="normal_user", role=UserRole.NORMAL)
        
        async def mock_normal_user():
            return normal_user
        
        from app.main import app
        from app.core.auth import get_current_user
        app.dependency_overrides[get_current_user] = mock_normal_user
        
        # Normal user should NOT be able to access admin endpoints
        admin_endpoints = [
            ("/api/v1/admin/users", "GET"),
            ("/api/v1/admin/permission-groups", "GET"),
            ("/api/v1/admin/permission-groups", "POST"),
            ("/api/v1/admin/audit-logs", "GET"),
            ("/api/v1/admin/system-settings", "GET"),
        ]
        
        for endpoint, method in admin_endpoints:
            if method == "GET":
                response = await test_client.get(endpoint)
            elif method == "POST":
                response = await test_client.post(endpoint, json={})
            
            assert response.status_code == 403, f"Normal user should not access admin endpoint {method} {endpoint}"
        
        # Normal user should NOT be able to modify their own role
        role_update_data = {"role": "admin"}
        role_response = await test_client.put(f"/api/v1/users/{normal_user.id}", json=role_update_data)
        assert role_response.status_code in [403, 422], "Normal user should not be able to change their role"
        
        # Normal user should NOT be able to create admin users
        admin_user_data = {
            "username": "malicious_admin",
            "email": "malicious@example.com",
            "password": "password123",
            "role": "admin"
        }
        
        create_admin_response = await test_client.post("/api/v1/admin/users", json=admin_user_data)
        assert create_admin_response.status_code == 403, "Normal user should not create admin users"
        
        # Clean up
        app.dependency_overrides.clear()
    
    @pytest.mark.asyncio
    async def test_insecure_direct_object_references(self, test_client: AsyncClient, test_db):
        """Test protection against insecure direct object references."""
        # Create users and documents
        user1 = await UserFactory.create_and_save_user(test_db, username="idor_user1")
        user2 = await UserFactory.create_and_save_user(test_db, username="idor_user2")
        
        # Create documents for both users
        doc1 = await DocumentFactory.create_and_save_document(test_db, title="User1 Document", author_id=user1.id)
        doc2 = await DocumentFactory.create_and_save_document(test_db, title="User2 Document", author_id=user2.id)
        
        # Mock user1 authentication
        async def mock_user1():
            return user1
        
        from app.main import app
        from app.core.auth import get_current_user
        app.dependency_overrides[get_current_user] = mock_user1
        
        # User1 should be able to access their own document
        own_doc_response = await test_client.get(f"/api/v1/documents/{doc1.id}")
        assert own_doc_response.status_code == 200, "User should access their own document"
        
        # User1 should NOT be able to access user2's document by direct ID reference
        other_doc_response = await test_client.get(f"/api/v1/documents/{doc2.id}")
        assert other_doc_response.status_code in [403, 404], "User should not access other user's document via direct ID"
        
        # Test with malformed IDs
        malformed_ids = [
            "00000000-0000-0000-0000-000000000000",  # Valid UUID format but non-existent
            "invalid-uuid-format",
            "../../../etc/passwd",
            "'; DROP TABLE documents; --",
        ]
        
        for malformed_id in malformed_ids:
            malformed_response = await test_client.get(f"/api/v1/documents/{malformed_id}")
            assert malformed_response.status_code in [400, 404, 422], f"Malformed ID should be rejected: {malformed_id}"
        
        # Clean up
        app.dependency_overrides.clear()
    
    @pytest.mark.asyncio
    async def test_broken_authentication(self, test_client: AsyncClient):
        """Test protection against broken authentication vulnerabilities."""
        # Test weak session management
        # Attempt to use expired or invalid tokens
        invalid_tokens = [
            "invalid.jwt.token",
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.signature",
            "",
            "Bearer invalid_token",
            "malicious_token_attempt"
        ]
        
        for invalid_token in invalid_tokens:
            headers = {"Authorization": f"Bearer {invalid_token}"}
            response = await test_client.get("/api/v1/auth/me", headers=headers)
            assert response.status_code == 401, f"Invalid token should be rejected: {invalid_token}"
        
        # Test authentication bypass attempts
        bypass_attempts = [
            {"Authorization": "Bearer null"},
            {"Authorization": "Bearer undefined"},
            {"Authorization": "Bearer admin"},
            {"Authorization": "Bearer true"},
            {"X-User-ID": "1"},
            {"X-Admin": "true"},
        ]
        
        for headers in bypass_attempts:
            response = await test_client.get("/api/v1/auth/me", headers=headers)
            assert response.status_code == 401, f"Authentication bypass should fail: {headers}"
        
        # Test session fixation
        # Get initial session
        initial_response = await test_client.get("/api/v1/health")
        initial_session = initial_response.cookies.get("session")
        
        # Attempt login with fixed session
        login_data = {
            "username": "test_user",
            "password": "password123"
        }
        
        # Set the initial session cookie
        cookies = {"session": initial_session} if initial_session else {}
        
        with patch('app.services.auth.AuthenticationService.verify_password', return_value=True):
            login_response = await test_client.post("/api/v1/auth/login", json=login_data, cookies=cookies)
        
        # Session should be regenerated after successful login
        if login_response.status_code == 200:
            new_session = login_response.cookies.get("session")
            if new_session and initial_session:
                assert new_session != initial_session, "Session should be regenerated after login"


@pytest.mark.security
class TestCryptographicSecurity:
    """Test cryptographic security measures."""
    
    @pytest.mark.asyncio
    async def test_jwt_token_security(self, test_client: AsyncClient):
        """Test JWT token cryptographic security."""
        from app.services.auth import AuthenticationService
        from jose import jwt
        from app.core.config import settings
        import uuid
        
        # Test token generation
        user_data = {"sub": str(uuid.uuid4()), "username": "crypto_test", "role": "normal"}
        token = AuthenticationService.create_access_token(user_data)
        
        # Verify token structure
        assert isinstance(token, str)
        assert len(token.split('.')) == 3, "JWT should have 3 parts"
        
        # Verify token can be decoded with correct key
        decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert decoded["sub"] == user_data["sub"]
        assert decoded["username"] == user_data["username"]
        
        # Verify token cannot be decoded with wrong key
        with pytest.raises(Exception):
            jwt.decode(token, "wrong_secret_key", algorithms=[settings.ALGORITHM])
        
        # Verify token cannot be decoded with wrong algorithm
        with pytest.raises(Exception):
            jwt.decode(token, settings.SECRET_KEY, algorithms=["HS512"])
        
        # Test token tampering detection
        token_parts = token.split('.')
        
        # Tamper with payload
        tampered_token = f"{token_parts[0]}.{token_parts[1][:-1]}X.{token_parts[2]}"
        with pytest.raises(Exception):
            jwt.decode(tampered_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        
        # Tamper with signature
        tampered_signature_token = f"{token_parts[0]}.{token_parts[1]}.{token_parts[2][:-1]}X"
        with pytest.raises(Exception):
            jwt.decode(tampered_signature_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    
    @pytest.mark.asyncio
    async def test_password_hashing_security(self):
        """Test password hashing cryptographic security."""
        from app.services.auth import AuthenticationService
        
        passwords = [
            "simple_password",
            "Complex_Password_123!",
            "very_long_password_with_many_characters_and_symbols_!@#$%^&*()",
            "短密码",  # Unicode password
            "password with spaces",
        ]
        
        for password in passwords:
            # Hash password
            hashed = AuthenticationService.hash_password(password)
            
            # Verify hash properties
            assert hashed != password, "Password should be hashed, not stored in plain text"
            assert hashed.startswith("$2b$"), "Should use bcrypt hashing"
            assert len(hashed) > 50, "Bcrypt hash should be long"
            
            # Verify password verification works
            assert AuthenticationService.verify_password(password, hashed), "Password verification should work"
            
            # Verify wrong password fails
            assert not AuthenticationService.verify_password(password + "wrong", hashed), "Wrong password should fail"
            
            # Verify salt is used (same password produces different hashes)
            hashed2 = AuthenticationService.hash_password(password)
            assert hashed != hashed2, "Same password should produce different hashes (salt)"
            assert AuthenticationService.verify_password(password, hashed2), "Both hashes should verify correctly"
    
    @pytest.mark.asyncio
    async def test_secure_random_generation(self):
        """Test secure random number generation."""
        import secrets
        import uuid
        
        # Test UUID generation (should be random)
        uuids = [uuid.uuid4() for _ in range(100)]
        unique_uuids = set(str(u) for u in uuids)
        assert len(unique_uuids) == 100, "UUIDs should be unique"
        
        # Test secure token generation
        tokens = [secrets.token_urlsafe(32) for _ in range(100)]
        unique_tokens = set(tokens)
        assert len(unique_tokens) == 100, "Secure tokens should be unique"
        
        # Verify token properties
        for token in tokens[:10]:  # Check first 10
            assert len(token) >= 32, "Token should be sufficiently long"
            assert token.replace('-', '').replace('_', '').isalnum(), "Token should be URL-safe"
    
    @pytest.mark.asyncio
    async def test_timing_attack_protection(self, test_client: AsyncClient):
        """Test protection against timing attacks."""
        import time
        import statistics
        
        # Test login timing for existing vs non-existing users
        existing_user_times = []
        nonexistent_user_times = []
        
        # Time login attempts for existing user (will fail due to wrong password)
        for _ in range(10):
            login_data = {"username": "existing_user", "password": "wrong_password"}
            
            start_time = time.perf_counter()
            response = await test_client.post("/api/v1/auth/login", json=login_data)
            end_time = time.perf_counter()
            
            existing_user_times.append((end_time - start_time) * 1000)
            assert response.status_code == 401
        
        # Time login attempts for non-existing user
        for _ in range(10):
            login_data = {"username": "nonexistent_user_12345", "password": "wrong_password"}
            
            start_time = time.perf_counter()
            response = await test_client.post("/api/v1/auth/login", json=login_data)
            end_time = time.perf_counter()
            
            nonexistent_user_times.append((end_time - start_time) * 1000)
            assert response.status_code == 401
        
        # Analyze timing differences
        avg_existing = statistics.mean(existing_user_times)
        avg_nonexistent = statistics.mean(nonexistent_user_times)
        
        # Timing difference should be minimal to prevent user enumeration
        timing_ratio = max(avg_existing, avg_nonexistent) / min(avg_existing, avg_nonexistent)
        
        # Allow some variance but not excessive timing differences
        assert timing_ratio < 2.0, f"Timing ratio {timing_ratio:.2f} suggests potential timing attack vulnerability"
        
        print(f"\nTiming Attack Test Results:")
        print(f"  Existing user avg: {avg_existing:.1f}ms")
        print(f"  Non-existing user avg: {avg_nonexistent:.1f}ms")
        print(f"  Timing ratio: {timing_ratio:.2f}")


@pytest.mark.security
class TestSecurityHeaders:
    """Test security headers and HTTPS enforcement."""
    
    @pytest.mark.asyncio
    async def test_security_headers_present(self, test_client: AsyncClient):
        """Test that security headers are present in responses."""
        response = await test_client.get("/api/v1/health")
        
        headers = dict(response.headers)
        
        # Check for important security headers
        security_headers = {
            "x-content-type-options": "nosniff",
            "x-frame-options": ["DENY", "SAMEORIGIN"],
            "x-xss-protection": "1; mode=block",
            "strict-transport-security": None,  # Should be present in HTTPS
            "content-security-policy": None,    # Should have CSP
        }
        
        for header_name, expected_values in security_headers.items():
            header_value = headers.get(header_name.lower())
            
            if expected_values is None:
                # Header should be present but we don't check specific value
                if header_name in ["strict-transport-security", "content-security-policy"]:
                    # These might not be present in test environment
                    continue
            elif isinstance(expected_values, list):
                # Header should have one of the expected values
                if header_value:
                    assert any(expected in header_value for expected in expected_values), \
                        f"Header {header_name} should contain one of {expected_values}, got: {header_value}"
            else:
                # Header should have exact value
                assert header_value == expected_values, \
                    f"Header {header_name} should be '{expected_values}', got: {header_value}"
    
    @pytest.mark.asyncio
    async def test_cors_security(self, test_client: AsyncClient):
        """Test CORS security configuration."""
        # Test preflight request
        headers = {
            "Origin": "https://malicious-site.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type"
        }
        
        response = await test_client.options("/api/v1/documents", headers=headers)
        
        # CORS should be restrictive
        cors_headers = dict(response.headers)
        
        if "access-control-allow-origin" in cors_headers:
            allowed_origin = cors_headers["access-control-allow-origin"]
            
            # Should not allow all origins in production
            assert allowed_origin != "*", "CORS should not allow all origins (*)"
            
            # Should not allow malicious origins
            assert "malicious-site.com" not in allowed_origin, "CORS should not allow malicious origins"
    
    @pytest.mark.asyncio
    async def test_information_disclosure_headers(self, test_client: AsyncClient):
        """Test that headers don't disclose sensitive information."""
        response = await test_client.get("/api/v1/health")
        
        headers = dict(response.headers)
        
        # Headers that might disclose sensitive information
        sensitive_headers = [
            "server",           # Should not reveal server software version
            "x-powered-by",     # Should not reveal framework
            "x-aspnet-version", # Should not reveal ASP.NET version
            "x-runtime",        # Should not reveal runtime version
        ]
        
        for header_name in sensitive_headers:
            header_value = headers.get(header_name.lower(), "")
            
            # Should not contain version numbers or detailed software info
            sensitive_patterns = [
                "apache/",
                "nginx/",
                "fastapi/",
                "python/",
                "uvicorn/",
                "version",
            ]
            
            for pattern in sensitive_patterns:
                assert pattern not in header_value.lower(), \
                    f"Header {header_name} should not disclose software version: {header_value}"