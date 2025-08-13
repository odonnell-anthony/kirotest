"""
Webhook API endpoints for GitHub and Azure DevOps integration.
"""
import uuid
import logging
import hmac
import hashlib
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, status, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User, UserRole
from app.services.webhook import WebhookService
from app.schemas.admin import WebhookConfigRequest, WebhookConfigResponse
from app.core.exceptions import NotFoundError, ValidationError, InternalError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency to require admin role."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user


@router.post("/", response_model=WebhookConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    webhook_data: WebhookConfigRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new webhook configuration (admin only).
    
    - **name**: Webhook name (required)
    - **url**: Webhook URL (required)
    - **secret**: Optional secret for webhook verification
    - **events**: List of events to trigger webhook
    - **is_active**: Whether webhook is active (default: true)
    """
    try:
        service = WebhookService(db)
        webhook = await service.create_webhook(webhook_data, current_user)
        return _to_webhook_response(webhook)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/", response_model=List[WebhookConfigResponse])
async def list_webhooks(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    List all webhook configurations (admin only).
    """
    try:
        service = WebhookService(db)
        webhooks = await service.list_webhooks()
        return [_to_webhook_response(webhook) for webhook in webhooks]
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{webhook_id}", response_model=WebhookConfigResponse)
async def get_webhook(
    webhook_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get webhook configuration by ID (admin only).
    
    - **webhook_id**: UUID of the webhook to retrieve
    """
    try:
        service = WebhookService(db)
        webhook = await service.get_webhook(webhook_id)
        return _to_webhook_response(webhook)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put("/{webhook_id}", response_model=WebhookConfigResponse)
async def update_webhook(
    webhook_id: uuid.UUID,
    webhook_data: WebhookConfigRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Update webhook configuration (admin only).
    
    - **webhook_id**: UUID of the webhook to update
    """
    try:
        service = WebhookService(db)
        webhook = await service.update_webhook(webhook_id, webhook_data, current_user)
        return _to_webhook_response(webhook)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete webhook configuration (admin only).
    
    - **webhook_id**: UUID of the webhook to delete
    """
    try:
        service = WebhookService(db)
        await service.delete_webhook(webhook_id, current_user)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/github", status_code=status.HTTP_200_OK)
async def github_webhook(
    request: Request,
    x_github_event: str = Header(..., alias="X-GitHub-Event"),
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
    db: AsyncSession = Depends(get_db)
):
    """
    GitHub webhook endpoint for repository integration.
    
    Handles GitHub events like push, pull request, issues, etc.
    Verifies webhook signature if configured.
    """
    try:
        # Get request body
        body = await request.body()
        
        # Parse JSON payload
        import json
        try:
            payload = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload"
            )
        
        service = WebhookService(db)
        
        # Verify signature if provided
        if x_hub_signature_256:
            await service.verify_github_signature(body, x_hub_signature_256)
        
        # Process the webhook event
        await service.process_github_webhook(x_github_event, payload)
        
        logger.info(f"Processed GitHub webhook event: {x_github_event}")
        return {"status": "success", "event": x_github_event}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing GitHub webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process webhook"
        )


@router.post("/azure-devops", status_code=status.HTTP_200_OK)
async def azure_devops_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Azure DevOps webhook endpoint for repository integration.
    
    Handles Azure DevOps events like code push, work item updates, etc.
    """
    try:
        # Get request body
        body = await request.body()
        
        # Parse JSON payload
        import json
        try:
            payload = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload"
            )
        
        # Extract event type from payload
        event_type = payload.get('eventType', 'unknown')
        
        service = WebhookService(db)
        
        # Process the webhook event
        await service.process_azure_devops_webhook(event_type, payload)
        
        logger.info(f"Processed Azure DevOps webhook event: {event_type}")
        return {"status": "success", "event": event_type}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing Azure DevOps webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process webhook"
        )


@router.post("/{webhook_id}/test", status_code=status.HTTP_200_OK)
async def test_webhook(
    webhook_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Test webhook by sending a test payload (admin only).
    
    - **webhook_id**: UUID of the webhook to test
    """
    try:
        service = WebhookService(db)
        result = await service.test_webhook(webhook_id)
        return result
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/github/link-issue", status_code=status.HTTP_200_OK)
async def link_github_issue(
    document_id: uuid.UUID,
    repo_name: str,
    issue_number: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Link a GitHub issue to a documentation page.
    
    - **document_id**: UUID of the document to link to
    - **repo_name**: GitHub repository name (owner/repo format)
    - **issue_number**: GitHub issue number
    """
    try:
        service = WebhookService(db)
        await service.link_github_issue_to_document(document_id, repo_name, issue_number, current_user)
        return {"status": "success", "message": f"Linked GitHub issue {repo_name}#{issue_number} to document"}
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/azure/link-work-item", status_code=status.HTTP_200_OK)
async def link_azure_work_item(
    document_id: uuid.UUID,
    work_item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Link an Azure DevOps work item to a documentation page.
    
    - **document_id**: UUID of the document to link to
    - **work_item_id**: Azure DevOps work item ID
    """
    try:
        service = WebhookService(db)
        await service.link_azure_work_item_to_document(document_id, work_item_id, current_user)
        return {"status": "success", "message": f"Linked Azure DevOps work item #{work_item_id} to document"}
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/github/issue-status/{repo_name}/{issue_number}", status_code=status.HTTP_200_OK)
async def get_github_issue_status(
    repo_name: str,
    issue_number: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current status of a GitHub issue.
    
    - **repo_name**: GitHub repository name (owner/repo format)
    - **issue_number**: GitHub issue number
    """
    try:
        service = WebhookService(db)
        status_info = await service.get_github_issue_status(repo_name, issue_number)
        return status_info
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/azure/work-item-status/{work_item_id}", status_code=status.HTTP_200_OK)
async def get_azure_work_item_status(
    work_item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current status of an Azure DevOps work item.
    
    - **work_item_id**: Azure DevOps work item ID
    """
    try:
        service = WebhookService(db)
        status_info = await service.get_azure_work_item_status(work_item_id)
        return status_info
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def _to_webhook_response(webhook) -> WebhookConfigResponse:
    """Convert Webhook model to WebhookConfigResponse schema."""
    return WebhookConfigResponse(
        id=str(webhook.id),
        name=webhook.name,
        url=webhook.url,
        events=webhook.events or [],
        is_active=webhook.is_active,
        created_at=webhook.created_at,
        last_triggered_at=webhook.last_triggered_at,
        success_count=webhook.success_count,
        failure_count=webhook.failure_count
    )