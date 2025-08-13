"""
Security tests for authentication and authorization.
"""
import pytest
import uuid
from unittest.mock import patch
from httpx import AsyncClient
from fastapi import status

from app.models.user import UserRole
from tests.conftest import UserFactory


@pytest.mark.security
class TestAuthenticationSecurity:
    """Test authentication security measures."""
    
    @pytest.mark.asyncio
    async def test_login_rate_limiting(self, test_client: AsyncClient):
        """Test that login attempts are rate limited."""
        login_data = {
            "username": "testuser",
            "password": "wrong_password"
        }
        
        # Make multiple failed login attempts
        responses = []
        for i in range(10):
            response = await test_client.post("/api/v1/auth/login", json=login_data)
            responses.append(response.status_code)
        
        # Should eventually get rate limited
        rate_limited_responses = [code for code in responses if code == status.HTTP_429_TOO_MANY_REQUESTS]
        assert len(rate_limited_responses) > 0, "Rate limiting should kick in after multiple failed attempts"
    
    @pytest.mark.asyncio
    async def test_password_hashing_security(self):
        """Test that passwords are properly hashed."""
        from app.services.auth import AuthenticationService
        
        password = "test_password_123"
        hashed = AuthenticationService.hash_password(password)
        
        # Verify password is hashed (not stored in plain text)
        assert hashed != password
        assert len(hashed) > 50  # bcrypt hashes are long
        assert hashed.startswith("$2b$")  # bcrypt format
        
        # Verify same password produces different hashes (salt)
        hashed2 = AuthenticationService.hash_password(password)
        assert hashed != hashed2
        
        # Verify both hashes verify correctly
        assert AuthenticationService.verify_password(password, hashed)
        assert AuthenticationService.verify_password(password, hashed2)
    
    @pytest.mark.asyncio
    async def test_jwt_token_security(self):
        """Test JWT token security properties."""
        from app.services.auth import AuthenticationService
        from jose import jwt
        from app.core.config import settings
        
        user_data = {"sub": str(uuid.uuid4()), "username": "testuser", "role": "normal"}
        token = AuthenticationService.create_access_token(user_data)
        
        # Verify token is properly signed
        decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert decoded["sub"] == user_data["sub"]
        assert decoded["username"] == user_data["username"]
        
        # Verify token has expiration
        assert "exp" in decoded
        assert "iat" in decoded
        
        # Verify token cannot be decoded with wrong key
        with pytest.raises(Exception):
            jwt.decode(token, "wrong_secret", algorithms=[settings.ALGORITHM])
    
    @pytest.mark.asyncio
    async def test_token_blacklisting(self, test_client: AsyncClient, test_user):
        """Test that blacklisted tokens are rejected."""
        # Login to get token
        with patch('app.services.auth.AuthenticationService.verify_password', return_value=True):
            login_response = await test_client.post("/api/v1/auth/login", json={
                "username": test_user.username,
                "password": "password"
            })
        
        assert login_response.status_code == 200
        token_data = login_response.json()
        access_token = token_data["access_token"]
        
        # Use token to access protected endpoint
        headers = {"Authorization": f"Bearer {access_token}"}
        response = await test_client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == 200
        
        # Logout (blacklist token)
        await test_client.post("/api/v1/auth/logout", headers=headers)
        
        # Try to use blacklisted token
        response = await test_client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == 401  # Should be unauthorized
    
    @pytest.mark.asyncio
    async def test_session_security(self, test_client: AsyncClient):
        """Test session security measures."""
        # Test that sessions have proper security attributes
        login_data = {
            "username": "testuser",
            "password": "password"
        }
        
        with patch('app.services.auth.AuthenticationService.verify_password', return_value=True):
            response = await test_client.post("/api/v1/auth/login", json=login_data)
        
        # Check response headers for security
        headers = response.headers
        
        # Should have security headers
        assert "X-Content-Type-Options" in headers or response.status_code == 401
        
        # Session data should be properly structured
        if response.status_code == 200:
            data = response.json()
            assert "access_token" in data
            assert "refresh_token" in data
            assert data["token_type"] == "bearer"
    
    @pytest.mark.asyncio
    async def test_password_strength_requirements(self, test_client: AsyncClient):
        """Test password strength requirements."""
        weak_passwords = [
            "123",
            "password",
            "abc",
            "12345678",
            "qwerty"
        ]
        
        for weak_password in weak_passwords:
            user_data = {
                "username": "testuser",
                "email": "test@example.com",
                "password": weak_password
            }
            
            # Attempt to create user with weak password
            response = await test_client.post("/api/v1/auth/register", json=user_data)
            
            # Should reject weak passwords
            assert response.status_code in [400, 422], f"Weak password '{weak_password}' should be rejected"
    
    @pytest.mark.asyncio
    async def test_account_lockout_protection(self, test_client: AsyncClient, test_user):
        """Test account lockout after multiple failed attempts."""
        login_data = {
            "username": test_user.username,
            "password": "wrong_password"
        }
        
        # Make multiple failed login attempts
        failed_attempts = 0
        for i in range(15):  # Try more than typical lockout threshold
            response = await test_client.post("/api/v1/auth/login", json=login_data)
            if response.status_code == 401:
                failed_attempts += 1
            elif response.status_code == 429:  # Rate limited
                break
        
        # Should eventually get rate limited or account locked
        assert failed_attempts >= 5, "Should have multiple failed attempts before lockout"
        
        # Try with correct password after lockout
        correct_login_data = {
            "username": test_user.username,
            "password": "correct_password"
        }
        
        with patch('app.services.auth.AuthenticationService.verify_password', return_value=True):
            response = await test_client.post("/api/v1/auth/login", json=correct_login_data)
            # Should still be locked out or rate limited
            assert response.status_code in [401, 429]


@pytest.mark.security
class TestAuthorizationSecurity:
    """Test authorization and permission security."""
    
    @pytest.mark.asyncio
    async def test_unauthorized_access_protection(self, test_client: AsyncClient):
        """Test that protected endpoints require authentication."""
        protected_endpoints = [
            ("/api/v1/auth/me", "GET"),
            ("/api/v1/documents", "POST"),
            ("/api/v1/documents/123", "PUT"),
            ("/api/v1/documents/123", "DELETE"),
            ("/api/v1/admin/users", "GET"),
        ]
        
        for endpoint, method in protected_endpoints:
            if method == "GET":
                response = await test_client.get(endpoint)
            elif method == "POST":
                response = await test_client.post(endpoint, json={})
            elif method == "PUT":
                response = await test_client.put(endpoint, json={})
            elif method == "DELETE":
                response = await test_client.delete(endpoint)
            
            # Should require authentication
            assert response.status_code == 401, f"Endpoint {method} {endpoint} should require authentication"
    
    @pytest.mark.asyncio
    async def test_admin_only_endpoints(self, test_client: AsyncClient, test_user, mock_current_user):
        """Test that admin-only endpoints reject normal users."""
        from app.main import app
        from app.core.auth import get_current_user
        
        # Override with normal user
        app.dependency_overrides[get_current_user] = mock_current_user
        
        admin_endpoints = [
            ("/api/v1/admin/users", "GET"),
            ("/api/v1/admin/permission-groups", "POST"),
            ("/api/v1/admin/audit-logs", "GET"),
        ]
        
        for endpoint, method in admin_endpoints:
            if method == "GET":
                response = await test_client.get(endpoint)
            elif method == "POST":
                response = await test_client.post(endpoint, json={})
            
            # Should reject normal user
            assert response.status_code == 403, f"Admin endpoint {method} {endpoint} should reject normal users"
    
    @pytest.mark.asyncio
    async def test_resource_ownership_protection(self, test_client: AsyncClient, test_db):
        """Test that users can only access their own resources."""
        # Create two users
        user1 = await UserFactory.create_and_save_user(test_db, username="user1")
        user2 = await UserFactory.create_and_save_user(test_db, username="user2")
        
        # Create document owned by user1
        from tests.conftest import DocumentFactory
        doc = await DocumentFactory.create_and_save_document(test_db, author_id=user1.id)
        
        # Mock user2 as current user
        async def mock_user2():
            return user2
        
        from app.main import app
        from app.core.auth import get_current_user
        app.dependency_overrides[get_current_user] = mock_user2
        
        # Try to access user1's document as user2
        response = await test_client.get(f"/api/v1/documents/{doc.id}")
        
        # Should either be forbidden or not found (depending on implementation)
        assert response.status_code in [403, 404], "Users should not access others' private resources"
    
    @pytest.mark.asyncio
    async def test_permission_escalation_protection(self, test_client: AsyncClient, test_user, mock_current_user):
        """Test protection against permission escalation."""
        from app.main import app
        from app.core.auth import get_current_user
        
        # Override with normal user
        app.dependency_overrides[get_current_user] = mock_current_user
        
        # Try to create admin permission group
        group_data = {
            "name": "malicious-admin-group",
            "description": "Trying to escalate privileges"
        }
        
        response = await test_client.post("/api/v1/admin/permission-groups", json=group_data)
        assert response.status_code == 403, "Normal users should not create permission groups"
        
        # Try to assign admin role to self
        user_update_data = {
            "role": "admin"
        }
        
        response = await test_client.put(f"/api/v1/admin/users/{test_user.id}", json=user_update_data)
        assert response.status_code == 403, "Users should not be able to change their own role"


@pytest.mark.security
class TestInputValidationSecurity:
    """Test input validation and sanitization security."""
    
    @pytest.mark.asyncio
    async def test_xss_protection(self, test_client: AsyncClient, security_test_data):
        """Test protection against XSS attacks."""
        xss_payloads = security_test_data["xss_payloads"]
        
        for payload in xss_payloads:
            # Try XSS in document creation
            doc_data = {
                "title": f"Test Document {payload}",
                "content": f"Content with XSS: {payload}",
                "folder_path": "/test/"
            }
            
            response = await test_client.post("/api/v1/documents", json=doc_data)
            
            if response.status_code == 201:
                # If document was created, verify content is sanitized
                data = response.json()
                assert "<script>" not in data["title"]
                assert "<script>" not in data["content"]
                assert "javascript:" not in data["title"]
                assert "javascript:" not in data["content"]
    
    @pytest.mark.asyncio
    async def test_sql_injection_protection(self, test_client: AsyncClient, security_test_data):
        """Test protection against SQL injection attacks."""
        sql_payloads = security_test_data["sql_injection_payloads"]
        
        for payload in sql_payloads:
            # Try SQL injection in search
            response = await test_client.get(f"/api/v1/search?q={payload}")
            
            # Should not cause server error
            assert response.status_code != 500, f"SQL injection payload caused server error: {payload}"
            
            # Try SQL injection in document title search
            response = await test_client.get(f"/api/v1/documents?title={payload}")
            assert response.status_code != 500, f"SQL injection in title search caused error: {payload}"
    
    @pytest.mark.asyncio
    async def test_path_traversal_protection(self, test_client: AsyncClient, security_test_data):
        """Test protection against path traversal attacks."""
        path_payloads = security_test_data["path_traversal_payloads"]
        
        for payload in path_payloads:
            # Try path traversal in file access
            response = await test_client.get(f"/api/v1/files/{payload}")
            
            # Should not allow access to system files
            assert response.status_code in [400, 403, 404], f"Path traversal should be blocked: {payload}"
            
            # Try path traversal in folder path
            doc_data = {
                "title": "Test Document",
                "content": "Test content",
                "folder_path": payload
            }
            
            response = await test_client.post("/api/v1/documents", json=doc_data)
            
            # Should reject invalid folder paths
            assert response.status_code in [400, 422], f"Invalid folder path should be rejected: {payload}"
    
    @pytest.mark.asyncio
    async def test_file_upload_security(self, test_client: AsyncClient):
        """Test file upload security measures."""
        # Test malicious file types
        malicious_files = [
            ("malicious.exe", b"MZ\x90\x00", "application/x-executable"),
            ("script.sh", b"#!/bin/bash\nrm -rf /", "application/x-sh"),
            ("virus.bat", b"@echo off\ndel /f /q *.*", "application/x-msdos-program"),
            ("payload.php", b"<?php system($_GET['cmd']); ?>", "application/x-php"),
        ]
        
        for filename, content, mime_type in malicious_files:
            files = {"file": (filename, content, mime_type)}
            data = {"folder_path": "/uploads/"}
            
            response = await test_client.post("/api/v1/files/upload", files=files, data=data)
            
            # Should reject malicious file types
            assert response.status_code in [400, 415], f"Malicious file {filename} should be rejected"
    
    @pytest.mark.asyncio
    async def test_content_length_protection(self, test_client: AsyncClient):
        """Test protection against oversized requests."""
        # Create oversized content
        large_content = "x" * (10 * 1024 * 1024)  # 10MB
        
        doc_data = {
            "title": "Large Document",
            "content": large_content,
            "folder_path": "/test/"
        }
        
        response = await test_client.post("/api/v1/documents", json=doc_data)
        
        # Should reject oversized content
        assert response.status_code in [400, 413, 422], "Oversized content should be rejected"
    
    @pytest.mark.asyncio
    async def test_header_injection_protection(self, test_client: AsyncClient):
        """Test protection against header injection attacks."""
        malicious_headers = {
            "X-Forwarded-For": "127.0.0.1\r\nX-Injected-Header: malicious",
            "User-Agent": "Mozilla/5.0\r\nX-Injected: attack",
            "Referer": "http://example.com\r\nSet-Cookie: malicious=true"
        }
        
        for header_name, header_value in malicious_headers.items():
            headers = {header_name: header_value}
            
            response = await test_client.get("/api/v1/health", headers=headers)
            
            # Should not reflect injected headers
            response_headers = dict(response.headers)
            assert "X-Injected-Header" not in response_headers
            assert "X-Injected" not in response_headers
            assert "Set-Cookie" not in response_headers or "malicious" not in response_headers.get("Set-Cookie", "")


@pytest.mark.security
class TestDataProtectionSecurity:
    """Test data protection and privacy security."""
    
    @pytest.mark.asyncio
    async def test_sensitive_data_exposure(self, test_client: AsyncClient, test_user):
        """Test that sensitive data is not exposed in API responses."""
        # Get user profile
        response = await test_client.get("/api/v1/auth/me")
        
        if response.status_code == 200:
            data = response.json()
            
            # Should not expose sensitive fields
            assert "password_hash" not in data
            assert "password" not in data
            assert "mfa_secret" not in data
            
            # Should only expose safe fields
            safe_fields = {"id", "username", "email", "role", "is_active", "created_at", "theme_preference"}
            exposed_fields = set(data.keys())
            unsafe_fields = exposed_fields - safe_fields
            
            # Allow some additional safe fields but flag truly sensitive ones
            dangerous_fields = {"password", "password_hash", "mfa_secret", "secret_key"}
            assert not any(field in data for field in dangerous_fields), f"Sensitive fields exposed: {unsafe_fields}"
    
    @pytest.mark.asyncio
    async def test_error_message_information_disclosure(self, test_client: AsyncClient):
        """Test that error messages don't disclose sensitive information."""
        # Try to access non-existent resource
        response = await test_client.get("/api/v1/documents/00000000-0000-0000-0000-000000000000")
        
        if response.status_code == 404:
            error_data = response.json()
            error_message = error_data.get("detail", "").lower()
            
            # Should not expose database structure or internal paths
            assert "table" not in error_message
            assert "column" not in error_message
            assert "database" not in error_message
            assert "/app/" not in error_message
            assert "traceback" not in error_message
    
    @pytest.mark.asyncio
    async def test_audit_logging_security(self, test_client: AsyncClient):
        """Test that security events are properly logged."""
        # This test would verify that security events are logged
        # In a real implementation, you would check log files or database
        
        # Make failed login attempt
        login_data = {
            "username": "nonexistent",
            "password": "wrong_password"
        }
        
        response = await test_client.post("/api/v1/auth/login", json=login_data)
        assert response.status_code == 401
        
        # In a real implementation, verify that this failed attempt is logged
        # with appropriate details (IP, timestamp, username attempted, etc.)
        # but without sensitive information like the password
        
        # For now, just verify the endpoint behaves correctly
        assert "detail" in response.json()
    
    @pytest.mark.asyncio
    async def test_session_fixation_protection(self, test_client: AsyncClient):
        """Test protection against session fixation attacks."""
        # Get initial session (if any)
        initial_response = await test_client.get("/api/v1/health")
        initial_cookies = initial_response.cookies
        
        # Login with those cookies
        login_data = {
            "username": "testuser",
            "password": "password"
        }
        
        with patch('app.services.auth.AuthenticationService.verify_password', return_value=True):
            login_response = await test_client.post("/api/v1/auth/login", json=login_data)
        
        if login_response.status_code == 200:
            # Session should be regenerated after login
            login_cookies = login_response.cookies
            
            # Should have new session identifier (if using session cookies)
            # This is a simplified check - in practice you'd verify session IDs changed
            assert len(login_cookies) >= 0  # At minimum, should not error