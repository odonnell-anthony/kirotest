"""
Webhook service for GitHub and Azure DevOps integration.
"""
import uuid
import logging
import hmac
import hashlib
import json
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import aiohttp

from app.models.user import User
from app.schemas.admin import WebhookConfigRequest
from app.core.exceptions import NotFoundError, ValidationError, InternalError
from app.services.github_integration import GitHubIntegrationService
from app.services.azure_devops_integration import AzureDevOpsIntegrationService

logger = logging.getLogger(__name__)


class WebhookConfig:
    """Simple webhook configuration model (placeholder)."""
    def __init__(self, id: uuid.UUID, name: str, url: str, secret: Optional[str], 
                 events: List[str], is_active: bool, created_at: datetime,
                 last_triggered_at: Optional[datetime] = None, 
                 success_count: int = 0, failure_count: int = 0):
        self.id = id
        self.name = name
        self.url = url
        self.secret = secret
        self.events = events
        self.is_active = is_active
        self.created_at = created_at
        self.last_triggered_at = last_triggered_at
        self.success_count = success_count
        self.failure_count = failure_count


class WebhookService:
    """Service for managing webhook operations."""
    
    def __init__(self, db: AsyncSession, github_token: Optional[str] = None,
                 azure_org: Optional[str] = None, azure_pat: Optional[str] = None):
        self.db = db
        # In-memory storage for demo purposes
        # In production, this would use a proper database table
        self._webhooks: Dict[uuid.UUID, WebhookConfig] = {}
        
        # Initialize integration services
        self.github_service = GitHubIntegrationService(db, github_token)
        self.azure_service = AzureDevOpsIntegrationService(db, azure_org, azure_pat)
    
    async def create_webhook(self, webhook_data: WebhookConfigRequest, user: User) -> WebhookConfig:
        """
        Create a new webhook configuration.
        
        Args:
            webhook_data: Webhook configuration data
            user: User creating the webhook
            
        Returns:
            Created webhook configuration
            
        Raises:
            ValidationError: If webhook data is invalid
            InternalError: If creation fails
        """
        try:
            # Validate webhook URL
            if not webhook_data.url.startswith(('http://', 'https://')):
                raise ValidationError("Webhook URL must be a valid HTTP/HTTPS URL")
            
            # Validate events
            valid_events = {
                'document.created', 'document.updated', 'document.deleted',
                'comment.created', 'comment.updated', 'comment.deleted',
                'user.created', 'user.updated'
            }
            
            for event in webhook_data.events:
                if event not in valid_events:
                    raise ValidationError(f"Invalid event type: {event}")
            
            # Create webhook
            webhook_id = uuid.uuid4()
            webhook = WebhookConfig(
                id=webhook_id,
                name=webhook_data.name,
                url=webhook_data.url,
                secret=webhook_data.secret,
                events=webhook_data.events,
                is_active=webhook_data.is_active,
                created_at=datetime.utcnow()
            )
            
            self._webhooks[webhook_id] = webhook
            
            logger.info(f"Created webhook: {webhook.name} by user {user.username}")
            return webhook
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error creating webhook: {e}")
            raise InternalError("Failed to create webhook")
    
    async def get_webhook(self, webhook_id: uuid.UUID) -> WebhookConfig:
        """
        Get webhook by ID.
        
        Args:
            webhook_id: Webhook ID
            
        Returns:
            Webhook configuration
            
        Raises:
            NotFoundError: If webhook not found
        """
        webhook = self._webhooks.get(webhook_id)
        if not webhook:
            raise NotFoundError(f"Webhook with ID {webhook_id} not found")
        return webhook
    
    async def list_webhooks(self) -> List[WebhookConfig]:
        """
        List all webhook configurations.
        
        Returns:
            List of webhook configurations
        """
        return list(self._webhooks.values())
    
    async def update_webhook(
        self, 
        webhook_id: uuid.UUID, 
        webhook_data: WebhookConfigRequest, 
        user: User
    ) -> WebhookConfig:
        """
        Update webhook configuration.
        
        Args:
            webhook_id: Webhook ID
            webhook_data: Updated webhook data
            user: User updating the webhook
            
        Returns:
            Updated webhook configuration
            
        Raises:
            NotFoundError: If webhook not found
            ValidationError: If webhook data is invalid
            InternalError: If update fails
        """
        try:
            webhook = await self.get_webhook(webhook_id)
            
            # Update fields
            webhook.name = webhook_data.name
            webhook.url = webhook_data.url
            webhook.secret = webhook_data.secret
            webhook.events = webhook_data.events
            webhook.is_active = webhook_data.is_active
            
            logger.info(f"Updated webhook: {webhook.name} by user {user.username}")
            return webhook
            
        except (NotFoundError, ValidationError):
            raise
        except Exception as e:
            logger.error(f"Error updating webhook {webhook_id}: {e}")
            raise InternalError("Failed to update webhook")
    
    async def delete_webhook(self, webhook_id: uuid.UUID, user: User) -> None:
        """
        Delete webhook configuration.
        
        Args:
            webhook_id: Webhook ID
            user: User deleting the webhook
            
        Raises:
            NotFoundError: If webhook not found
            InternalError: If deletion fails
        """
        try:
            webhook = await self.get_webhook(webhook_id)
            del self._webhooks[webhook_id]
            
            logger.info(f"Deleted webhook: {webhook.name} by user {user.username}")
            
        except NotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error deleting webhook {webhook_id}: {e}")
            raise InternalError("Failed to delete webhook")
    
    async def verify_github_signature(self, body: bytes, signature: str) -> None:
        """
        Verify GitHub webhook signature.
        
        Args:
            body: Request body
            signature: GitHub signature header
            
        Raises:
            ValidationError: If signature is invalid
        """
        # For demo purposes, we'll skip signature verification
        # In production, you would:
        # 1. Get the webhook secret from configuration
        # 2. Calculate HMAC-SHA256 of the body using the secret
        # 3. Compare with the provided signature
        logger.info("GitHub signature verification (demo mode)")
    
    async def process_github_webhook(self, event_type: str, payload: Dict[str, Any]) -> None:
        """
        Process GitHub webhook event.
        
        Args:
            event_type: GitHub event type
            payload: Event payload
        """
        try:
            logger.info(f"Processing GitHub event: {event_type}")
            
            # Handle different GitHub events using the integration service
            if event_type == "push":
                await self.github_service.process_push_event(payload)
            elif event_type == "pull_request":
                await self.github_service.process_pull_request_event(payload)
            elif event_type == "issues":
                await self.github_service.process_issues_event(payload)
            else:
                logger.info(f"Unhandled GitHub event type: {event_type}")
            
            # Trigger configured webhooks
            await self._trigger_webhooks(f"github.{event_type}", payload)
            
        except Exception as e:
            logger.error(f"Error processing GitHub webhook: {e}")
            raise
    
    async def process_azure_devops_webhook(self, event_type: str, payload: Dict[str, Any]) -> None:
        """
        Process Azure DevOps webhook event.
        
        Args:
            event_type: Azure DevOps event type
            payload: Event payload
        """
        try:
            logger.info(f"Processing Azure DevOps event: {event_type}")
            
            # Handle different Azure DevOps events using the integration service
            if event_type == "git.push":
                await self.azure_service.process_git_push_event(payload)
            elif event_type in ["git.pullrequest.created", "git.pullrequest.updated"]:
                await self.azure_service.process_pull_request_event(payload)
            elif event_type == "workitem.updated":
                await self.azure_service.process_work_item_event(payload)
            elif event_type in ["build.complete", "build.started"]:
                await self.azure_service.process_build_event(payload)
            else:
                logger.info(f"Unhandled Azure DevOps event type: {event_type}")
            
            # Trigger configured webhooks
            await self._trigger_webhooks(f"azure.{event_type}", payload)
            
        except Exception as e:
            logger.error(f"Error processing Azure DevOps webhook: {e}")
            raise
    
    async def test_webhook(self, webhook_id: uuid.UUID) -> Dict[str, Any]:
        """
        Test webhook by sending a test payload.
        
        Args:
            webhook_id: Webhook ID
            
        Returns:
            Test result
            
        Raises:
            NotFoundError: If webhook not found
            InternalError: If test fails
        """
        try:
            webhook = await self.get_webhook(webhook_id)
            
            if not webhook.is_active:
                raise ValidationError("Cannot test inactive webhook")
            
            # Create test payload
            test_payload = {
                "event": "webhook.test",
                "timestamp": datetime.utcnow().isoformat(),
                "data": {
                    "message": "This is a test webhook payload",
                    "webhook_id": str(webhook_id)
                }
            }
            
            # Send test request
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    webhook.url,
                    json=test_payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    success = response.status < 400
                    
                    if success:
                        webhook.success_count += 1
                    else:
                        webhook.failure_count += 1
                    
                    webhook.last_triggered_at = datetime.utcnow()
                    
                    return {
                        "success": success,
                        "status_code": response.status,
                        "response_text": await response.text()
                    }
            
        except NotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error testing webhook {webhook_id}: {e}")
            raise InternalError("Failed to test webhook")
    
    async def link_github_issue_to_document(self, document_id: uuid.UUID, repo_name: str, 
                                           issue_number: int, user: User) -> None:
        """
        Link a GitHub issue to a documentation page.
        
        Args:
            document_id: Document ID to link to
            repo_name: GitHub repository name (owner/repo)
            issue_number: GitHub issue number
            user: User creating the link
        """
        await self.github_service.link_issue_to_document(document_id, repo_name, issue_number, user)
    
    async def link_azure_work_item_to_document(self, document_id: uuid.UUID, work_item_id: int, 
                                             user: User) -> None:
        """
        Link an Azure DevOps work item to a documentation page.
        
        Args:
            document_id: Document ID to link to
            work_item_id: Azure DevOps work item ID
            user: User creating the link
        """
        await self.azure_service.link_work_item_to_document(document_id, work_item_id, user)
    
    async def get_github_issue_status(self, repo_name: str, issue_number: int) -> Dict[str, Any]:
        """
        Get current status of a GitHub issue.
        
        Args:
            repo_name: GitHub repository name (owner/repo)
            issue_number: GitHub issue number
            
        Returns:
            Issue status information
        """
        return await self.github_service.get_issue_status(repo_name, issue_number)
    
    async def get_azure_work_item_status(self, work_item_id: int) -> Dict[str, Any]:
        """
        Get current status of an Azure DevOps work item.
        
        Args:
            work_item_id: Azure DevOps work item ID
            
        Returns:
            Work item status information
        """
        return await self.azure_service.get_work_item_status(work_item_id)
    
    async def process_github_mentions(self, content: str, repo_name: str) -> str:
        """
        Process @mentions in content for GitHub integration.
        
        Args:
            content: Content with potential @mentions
            repo_name: GitHub repository name for context
            
        Returns:
            Content with processed mentions
        """
        return await self.github_service.process_mentions(content, repo_name)
    
    async def process_azure_mentions(self, content: str, project_name: str) -> str:
        """
        Process @mentions in content for Azure DevOps integration.
        
        Args:
            content: Content with potential @mentions
            project_name: Azure DevOps project name for context
            
        Returns:
            Content with processed mentions
        """
        return await self.azure_service.process_mentions(content, project_name)
    
    async def _trigger_webhooks(self, event: str, payload: Dict[str, Any]) -> None:
        """
        Trigger configured webhooks for an event.
        
        Args:
            event: Event name
            payload: Event payload
        """
        for webhook in self._webhooks.values():
            if webhook.is_active and event in webhook.events:
                try:
                    await self._send_webhook(webhook, event, payload)
                except Exception as e:
                    logger.error(f"Failed to send webhook {webhook.id}: {e}")
    
    async def _send_webhook(self, webhook: WebhookConfig, event: str, payload: Dict[str, Any]) -> None:
        """
        Send webhook HTTP request.
        
        Args:
            webhook: Webhook configuration
            event: Event name
            payload: Event payload
        """
        webhook_payload = {
            "event": event,
            "timestamp": datetime.utcnow().isoformat(),
            "data": payload
        }
        
        headers = {"Content-Type": "application/json"}
        
        # Add signature if secret is configured
        if webhook.secret:
            signature = hmac.new(
                webhook.secret.encode(),
                json.dumps(webhook_payload).encode(),
                hashlib.sha256
            ).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={signature}"
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook.url,
                json=webhook_payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status < 400:
                    webhook.success_count += 1
                    logger.info(f"Webhook {webhook.id} sent successfully")
                else:
                    webhook.failure_count += 1
                    logger.warning(f"Webhook {webhook.id} failed: {response.status}")
                
                webhook.last_triggered_at = datetime.utcnow()