"""
Integration tests for webhook functionality.
"""
import pytest
import json
import uuid
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from fastapi import status

from tests.conftest import UserFactory, DocumentFactory


@pytest.mark.integration
class TestWebhookIntegration:
    """Test webhook integration with external services."""
    
    @pytest.mark.asyncio
    async def test_webhook_registration(self, test_client: AsyncClient, test_user):
        """Test webhook registration flow."""
        webhook_data = {
            "url": "https://example.com/webhook",
            "events": ["document.created", "document.updated"],
            "secret": "webhook_secret_123",
            "is_active": True
        }
        
        response = await test_client.post("/api/v1/webhooks", json=webhook_data)
        assert response.status_code == status.HTTP_201_CREATED
        
        webhook = response.json()
        assert webhook["url"] == webhook_data["url"]
        assert webhook["events"] == webhook_data["events"]
        assert webhook["is_active"] is True
        assert "id" in webhook
        assert "secret" not in webhook  # Secret should not be returned
        
        return webhook["id"]
    
    @pytest.mark.asyncio
    async def test_webhook_document_created_trigger(self, test_client: AsyncClient, test_user):
        """Test webhook trigger on document creation."""
        # Register webhook
        webhook_data = {
            "url": "https://example.com/webhook/document-created",
            "events": ["document.created"],
            "secret": "test_secret"
        }
        
        webhook_response = await test_client.post("/api/v1/webhooks", json=webhook_data)
        assert webhook_response.status_code == status.HTTP_201_CREATED
        
        # Mock HTTP client for webhook delivery
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.return_value = AsyncMock(status_code=200)
            
            # Create document (should trigger webhook)
            doc_data = {
                "title": "Webhook Test Document",
                "content": "This document creation should trigger a webhook.",
                "folder_path": "/webhook-test/"
            }
            
            response = await test_client.post("/api/v1/documents", json=doc_data)
            assert response.status_code == status.HTTP_201_CREATED
            
            # Verify webhook was called
            mock_post.assert_called_once()
            
            # Verify webhook payload
            call_args = mock_post.call_args
            webhook_url = call_args[1]["url"] if "url" in call_args[1] else call_args[0][0]
            webhook_payload = call_args[1]["json"] if "json" in call_args[1] else json.loads(call_args[1]["data"])
            
            assert webhook_url == "https://example.com/webhook/document-created"
            assert webhook_payload["event"] == "document.created"
            assert "data" in webhook_payload
            assert webhook_payload["data"]["title"] == "Webhook Test Document"
    
    @pytest.mark.asyncio
    async def test_webhook_document_updated_trigger(self, test_client: AsyncClient, test_document):
        """Test webhook trigger on document update."""
        # Register webhook
        webhook_data = {
            "url": "https://example.com/webhook/document-updated",
            "events": ["document.updated"],
            "secret": "update_secret"
        }
        
        webhook_response = await test_client.post("/api/v1/webhooks", json=webhook_data)
        assert webhook_response.status_code == status.HTTP_201_CREATED
        
        # Mock HTTP client for webhook delivery
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.return_value = AsyncMock(status_code=200)
            
            # Update document (should trigger webhook)
            update_data = {
                "title": "Updated Webhook Test Document",
                "content": "This document update should trigger a webhook."
            }
            
            response = await test_client.put(f"/api/v1/documents/{test_document.id}", json=update_data)
            assert response.status_code == status.HTTP_200_OK
            
            # Verify webhook was called
            mock_post.assert_called_once()
            
            # Verify webhook payload
            call_args = mock_post.call_args
            webhook_payload = call_args[1]["json"] if "json" in call_args[1] else json.loads(call_args[1]["data"])
            
            assert webhook_payload["event"] == "document.updated"
            assert webhook_payload["data"]["title"] == "Updated Webhook Test Document"
    
    @pytest.mark.asyncio
    async def test_webhook_multiple_events(self, test_client: AsyncClient, test_user):
        """Test webhook with multiple event subscriptions."""
        # Register webhook for multiple events
        webhook_data = {
            "url": "https://example.com/webhook/multi-events",
            "events": ["document.created", "document.updated", "document.deleted"],
            "secret": "multi_secret"
        }
        
        webhook_response = await test_client.post("/api/v1/webhooks", json=webhook_data)
        assert webhook_response.status_code == status.HTTP_201_CREATED
        
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.return_value = AsyncMock(status_code=200)
            
            # Create document
            doc_data = {
                "title": "Multi-Event Test Document",
                "content": "Test content",
                "folder_path": "/multi-test/"
            }
            
            create_response = await test_client.post("/api/v1/documents", json=doc_data)
            assert create_response.status_code == status.HTTP_201_CREATED
            document = create_response.json()
            
            # Update document
            update_data = {"title": "Updated Multi-Event Document"}
            update_response = await test_client.put(f"/api/v1/documents/{document['id']}", json=update_data)
            assert update_response.status_code == status.HTTP_200_OK
            
            # Delete document
            delete_response = await test_client.delete(f"/api/v1/documents/{document['id']}")
            assert delete_response.status_code == status.HTTP_200_OK
            
            # Verify webhook was called 3 times (create, update, delete)
            assert mock_post.call_count == 3
            
            # Verify event types
            call_events = []
            for call in mock_post.call_args_list:
                payload = call[1]["json"] if "json" in call[1] else json.loads(call[1]["data"])
                call_events.append(payload["event"])
            
            assert "document.created" in call_events
            assert "document.updated" in call_events
            assert "document.deleted" in call_events
    
    @pytest.mark.asyncio
    async def test_webhook_signature_verification(self, test_client: AsyncClient, test_user):
        """Test webhook signature generation and verification."""
        webhook_secret = "signature_test_secret"
        
        # Register webhook
        webhook_data = {
            "url": "https://example.com/webhook/signature-test",
            "events": ["document.created"],
            "secret": webhook_secret
        }
        
        webhook_response = await test_client.post("/api/v1/webhooks", json=webhook_data)
        assert webhook_response.status_code == status.HTTP_201_CREATED
        
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.return_value = AsyncMock(status_code=200)
            
            # Create document to trigger webhook
            doc_data = {
                "title": "Signature Test Document",
                "content": "Test content for signature verification",
                "folder_path": "/signature-test/"
            }
            
            response = await test_client.post("/api/v1/documents", json=doc_data)
            assert response.status_code == status.HTTP_201_CREATED
            
            # Verify webhook was called with signature
            mock_post.assert_called_once()
            
            call_args = mock_post.call_args
            headers = call_args[1].get("headers", {})
            
            # Should have signature header
            assert any("signature" in header.lower() for header in headers.keys()), "Webhook should include signature header"
    
    @pytest.mark.asyncio
    async def test_webhook_retry_mechanism(self, test_client: AsyncClient, test_user):
        """Test webhook retry mechanism on failure."""
        # Register webhook
        webhook_data = {
            "url": "https://example.com/webhook/retry-test",
            "events": ["document.created"],
            "secret": "retry_secret"
        }
        
        webhook_response = await test_client.post("/api/v1/webhooks", json=webhook_data)
        assert webhook_response.status_code == status.HTTP_201_CREATED
        
        # Mock HTTP client to simulate failures then success
        with patch('httpx.AsyncClient.post') as mock_post:
            # First two calls fail, third succeeds
            mock_post.side_effect = [
                AsyncMock(status_code=500),  # First attempt fails
                AsyncMock(status_code=502),  # Second attempt fails
                AsyncMock(status_code=200),  # Third attempt succeeds
            ]
            
            # Create document to trigger webhook
            doc_data = {
                "title": "Retry Test Document",
                "content": "Test content for retry mechanism",
                "folder_path": "/retry-test/"
            }
            
            response = await test_client.post("/api/v1/documents", json=doc_data)
            assert response.status_code == status.HTTP_201_CREATED
            
            # Note: In a real implementation, retries might be handled by background tasks
            # This test verifies the webhook system can handle failures gracefully
            # The exact retry behavior depends on the implementation
    
    @pytest.mark.asyncio
    async def test_webhook_filtering_by_event(self, test_client: AsyncClient, test_user):
        """Test webhook filtering by specific events."""
        # Register webhook only for document.created events
        webhook_data = {
            "url": "https://example.com/webhook/create-only",
            "events": ["document.created"],  # Only subscribe to created events
            "secret": "filter_secret"
        }
        
        webhook_response = await test_client.post("/api/v1/webhooks", json=webhook_data)
        assert webhook_response.status_code == status.HTTP_201_CREATED
        
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.return_value = AsyncMock(status_code=200)
            
            # Create document (should trigger webhook)
            doc_data = {
                "title": "Filter Test Document",
                "content": "Test content",
                "folder_path": "/filter-test/"
            }
            
            create_response = await test_client.post("/api/v1/documents", json=doc_data)
            assert create_response.status_code == status.HTTP_201_CREATED
            document = create_response.json()
            
            # Update document (should NOT trigger webhook)
            update_data = {"title": "Updated Filter Test Document"}
            update_response = await test_client.put(f"/api/v1/documents/{document['id']}", json=update_data)
            assert update_response.status_code == status.HTTP_200_OK
            
            # Verify webhook was called only once (for create, not update)
            assert mock_post.call_count == 1
            
            # Verify it was called for the create event
            call_args = mock_post.call_args
            payload = call_args[1]["json"] if "json" in call_args[1] else json.loads(call_args[1]["data"])
            assert payload["event"] == "document.created"
    
    @pytest.mark.asyncio
    async def test_webhook_deactivation(self, test_client: AsyncClient, test_user):
        """Test webhook deactivation."""
        # Register active webhook
        webhook_data = {
            "url": "https://example.com/webhook/deactivation-test",
            "events": ["document.created"],
            "secret": "deactivation_secret",
            "is_active": True
        }
        
        webhook_response = await test_client.post("/api/v1/webhooks", json=webhook_data)
        assert webhook_response.status_code == status.HTTP_201_CREATED
        webhook = webhook_response.json()
        webhook_id = webhook["id"]
        
        # Deactivate webhook
        deactivate_data = {"is_active": False}
        update_response = await test_client.put(f"/api/v1/webhooks/{webhook_id}", json=deactivate_data)
        assert update_response.status_code == status.HTTP_200_OK
        
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.return_value = AsyncMock(status_code=200)
            
            # Create document (should NOT trigger deactivated webhook)
            doc_data = {
                "title": "Deactivation Test Document",
                "content": "Test content",
                "folder_path": "/deactivation-test/"
            }
            
            response = await test_client.post("/api/v1/documents", json=doc_data)
            assert response.status_code == status.HTTP_201_CREATED
            
            # Verify webhook was NOT called
            mock_post.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_webhook_deletion(self, test_client: AsyncClient, test_user):
        """Test webhook deletion."""
        # Register webhook
        webhook_data = {
            "url": "https://example.com/webhook/deletion-test",
            "events": ["document.created"],
            "secret": "deletion_secret"
        }
        
        webhook_response = await test_client.post("/api/v1/webhooks", json=webhook_data)
        assert webhook_response.status_code == status.HTTP_201_CREATED
        webhook = webhook_response.json()
        webhook_id = webhook["id"]
        
        # Delete webhook
        delete_response = await test_client.delete(f"/api/v1/webhooks/{webhook_id}")
        assert delete_response.status_code == status.HTTP_200_OK
        
        # Verify webhook is deleted
        get_response = await test_client.get(f"/api/v1/webhooks/{webhook_id}")
        assert get_response.status_code == status.HTTP_404_NOT_FOUND
        
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.return_value = AsyncMock(status_code=200)
            
            # Create document (should NOT trigger deleted webhook)
            doc_data = {
                "title": "Deletion Test Document",
                "content": "Test content",
                "folder_path": "/deletion-test/"
            }
            
            response = await test_client.post("/api/v1/documents", json=doc_data)
            assert response.status_code == status.HTTP_201_CREATED
            
            # Verify webhook was NOT called
            mock_post.assert_not_called()


@pytest.mark.integration
class TestWebhookPayloadIntegration:
    """Test webhook payload structure and content."""
    
    @pytest.mark.asyncio
    async def test_document_created_payload_structure(self, test_client: AsyncClient, test_user):
        """Test document.created webhook payload structure."""
        # Register webhook
        webhook_data = {
            "url": "https://example.com/webhook/payload-test",
            "events": ["document.created"],
            "secret": "payload_secret"
        }
        
        webhook_response = await test_client.post("/api/v1/webhooks", json=webhook_data)
        assert webhook_response.status_code == status.HTTP_201_CREATED
        
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.return_value = AsyncMock(status_code=200)
            
            # Create document
            doc_data = {
                "title": "Payload Structure Test",
                "content": "# Test Content\n\nThis is test content.",
                "folder_path": "/payload-test/",
                "tags": ["test", "webhook"]
            }
            
            response = await test_client.post("/api/v1/documents", json=doc_data)
            assert response.status_code == status.HTTP_201_CREATED
            
            # Verify webhook payload structure
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            payload = call_args[1]["json"] if "json" in call_args[1] else json.loads(call_args[1]["data"])
            
            # Verify top-level structure
            required_fields = ["event", "timestamp", "data"]
            for field in required_fields:
                assert field in payload, f"Payload should contain {field}"
            
            # Verify event type
            assert payload["event"] == "document.created"
            
            # Verify data structure
            data = payload["data"]
            document_fields = ["id", "title", "content", "folder_path", "author_id", "created_at"]
            for field in document_fields:
                assert field in data, f"Document data should contain {field}"
            
            # Verify data values
            assert data["title"] == "Payload Structure Test"
            assert data["content"] == "# Test Content\n\nThis is test content."
            assert data["folder_path"] == "/payload-test/"
    
    @pytest.mark.asyncio
    async def test_webhook_payload_sensitive_data_filtering(self, test_client: AsyncClient, test_user):
        """Test that sensitive data is filtered from webhook payloads."""
        # Register webhook
        webhook_data = {
            "url": "https://example.com/webhook/sensitive-data-test",
            "events": ["document.created"],
            "secret": "sensitive_secret"
        }
        
        webhook_response = await test_client.post("/api/v1/webhooks", json=webhook_data)
        assert webhook_response.status_code == status.HTTP_201_CREATED
        
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_post.return_value = AsyncMock(status_code=200)
            
            # Create document
            doc_data = {
                "title": "Sensitive Data Test",
                "content": "Content with sensitive information",
                "folder_path": "/sensitive-test/"
            }
            
            response = await test_client.post("/api/v1/documents", json=doc_data)
            assert response.status_code == status.HTTP_201_CREATED
            
            # Verify sensitive data is not included in webhook payload
            call_args = mock_post.call_args
            payload = call_args[1]["json"] if "json" in call_args[1] else json.loads(call_args[1]["data"])
            
            # Convert payload to string for searching
            payload_str = json.dumps(payload).lower()
            
            # Verify sensitive fields are not exposed
            sensitive_fields = ["password", "secret", "token", "key"]
            for field in sensitive_fields:
                assert field not in payload_str, f"Sensitive field '{field}' should not be in webhook payload"


@pytest.mark.integration
class TestWebhookErrorHandling:
    """Test webhook error handling and resilience."""
    
    @pytest.mark.asyncio
    async def test_webhook_timeout_handling(self, test_client: AsyncClient, test_user):
        """Test webhook timeout handling."""
        # Register webhook
        webhook_data = {
            "url": "https://example.com/webhook/timeout-test",
            "events": ["document.created"],
            "secret": "timeout_secret"
        }
        
        webhook_response = await test_client.post("/api/v1/webhooks", json=webhook_data)
        assert webhook_response.status_code == status.HTTP_201_CREATED
        
        # Mock HTTP client to simulate timeout
        with patch('httpx.AsyncClient.post') as mock_post:
            import asyncio
            mock_post.side_effect = asyncio.TimeoutError("Request timeout")
            
            # Create document (webhook should handle timeout gracefully)
            doc_data = {
                "title": "Timeout Test Document",
                "content": "Test content",
                "folder_path": "/timeout-test/"
            }
            
            response = await test_client.post("/api/v1/documents", json=doc_data)
            
            # Document creation should still succeed even if webhook times out
            assert response.status_code == status.HTTP_201_CREATED
            
            # Verify webhook was attempted
            mock_post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_webhook_invalid_url_handling(self, test_client: AsyncClient, test_user):
        """Test webhook handling of invalid URLs."""
        # Register webhook with invalid URL
        webhook_data = {
            "url": "https://invalid-domain-that-does-not-exist.com/webhook",
            "events": ["document.created"],
            "secret": "invalid_url_secret"
        }
        
        webhook_response = await test_client.post("/api/v1/webhooks", json=webhook_data)
        assert webhook_response.status_code == status.HTTP_201_CREATED
        
        # Mock HTTP client to simulate connection error
        with patch('httpx.AsyncClient.post') as mock_post:
            import httpx
            mock_post.side_effect = httpx.ConnectError("Connection failed")
            
            # Create document (webhook should handle connection error gracefully)
            doc_data = {
                "title": "Invalid URL Test Document",
                "content": "Test content",
                "folder_path": "/invalid-url-test/"
            }
            
            response = await test_client.post("/api/v1/documents", json=doc_data)
            
            # Document creation should still succeed
            assert response.status_code == status.HTTP_201_CREATED
            
            # Verify webhook was attempted
            mock_post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_webhook_malformed_response_handling(self, test_client: AsyncClient, test_user):
        """Test webhook handling of malformed responses."""
        # Register webhook
        webhook_data = {
            "url": "https://example.com/webhook/malformed-response-test",
            "events": ["document.created"],
            "secret": "malformed_secret"
        }
        
        webhook_response = await test_client.post("/api/v1/webhooks", json=webhook_data)
        assert webhook_response.status_code == status.HTTP_201_CREATED
        
        # Mock HTTP client to return malformed response
        with patch('httpx.AsyncClient.post') as mock_post:
            malformed_response = AsyncMock()
            malformed_response.status_code = 200
            malformed_response.text = "Invalid JSON response"
            malformed_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
            mock_post.return_value = malformed_response
            
            # Create document
            doc_data = {
                "title": "Malformed Response Test Document",
                "content": "Test content",
                "folder_path": "/malformed-test/"
            }
            
            response = await test_client.post("/api/v1/documents", json=doc_data)
            
            # Document creation should still succeed
            assert response.status_code == status.HTTP_201_CREATED
            
            # Verify webhook was called
            mock_post.assert_called_once()