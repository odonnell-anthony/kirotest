"""
Document API endpoints for content management.
"""
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.document import DocumentStatus
from app.services.document import DocumentService
from app.schemas.document import (
    DocumentCreate, DocumentUpdate, DocumentMoveRequest,
    DocumentRevisionResponse, DocumentRevisionListResponse,
    DocumentRevisionRestoreRequest, DocumentRevisionComparisonResponse
)
from app.schemas.responses import (
    DocumentResponse, DocumentListResponse
)
from app.core.exceptions import (
    NotFoundError, PermissionDeniedError, ValidationError,
    DuplicateError, InternalError
)

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


@router.post("/", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(
    doc_data: DocumentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new document.
    
    - **title**: Document title (required)
    - **content**: Document content in markdown or HTML
    - **folder_path**: Folder path for organization (default: "/")
    - **content_type**: Content format (markdown or html)
    - **status**: Document status (draft or published)
    - **tags**: List of tag names
    """
    try:
        service = DocumentService(db)
        document = await service.create_document(doc_data, current_user)
        return _to_document_response(document)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
    except DuplicateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a document by ID.
    
    Returns the document if:
    - Document is published (visible to all users)
    - Document is draft and user is the author
    - User is admin (can see all documents)
    """
    try:
        service = DocumentService(db)
        document = await service.get_document(document_id, current_user)
        return _to_document_response(document)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)


@router.put("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: uuid.UUID,
    doc_data: DocumentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update an existing document.
    
    Only the document author or admin can update a document.
    """
    try:
        service = DocumentService(db)
        document = await service.update_document(
            document_id, 
            doc_data, 
            current_user, 
            change_summary=doc_data.change_summary
        )
        return _to_document_response(document)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=e.message)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
    except DuplicateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a document.
    
    Only the document author or admin can delete a document.
    """
    try:
        service = DocumentService(db)
        await service.delete_document(document_id, current_user)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=e.message)
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)


@router.post("/{document_id}/move", response_model=DocumentResponse)
async def move_document(
    document_id: uuid.UUID,
    move_data: DocumentMoveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Move a document to a different folder.
    
    Only the document author or admin can move a document.
    """
    try:
        service = DocumentService(db)
        document = await service.move_document(document_id, move_data.new_folder_path, current_user)
        return _to_document_response(document)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=e.message)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
    except DuplicateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)


@router.get("/", response_model=List[DocumentListResponse])
async def list_documents(
    folder_path: Optional[str] = Query(None, description="Filter by folder path"),
    status: Optional[DocumentStatus] = Query(None, description="Filter by document status"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of documents to return"),
    offset: int = Query(0, ge=0, description="Number of documents to skip"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List documents with optional filtering and pagination.
    
    Returns documents based on visibility rules:
    - Published documents are visible to all users
    - Draft documents are only visible to their authors
    - Admins can see all documents
    """
    try:
        service = DocumentService(db)
        documents = await service.list_documents(
            user=current_user,
            folder_path=folder_path,
            status=status,
            limit=limit,
            offset=offset
        )
        return [_to_document_list_response(doc) for doc in documents]
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)


def _to_document_response(document) -> DocumentResponse:
    """Convert Document model to DocumentResponse schema."""
    from app.schemas.responses import TagResponse
    
    tags = []
    for doc_tag in document.tags:
        tags.append(TagResponse(
            id=str(doc_tag.tag.id),
            name=doc_tag.tag.name,
            description=doc_tag.tag.description,
            color=doc_tag.tag.color,
            usage_count=doc_tag.tag.usage_count
        ))
    
    return DocumentResponse(
        id=str(document.id),
        title=document.title,
        slug=document.slug,
        content=document.content,
        content_type=document.content_type,
        folder_path=document.folder_path,
        status=document.status,
        author_id=str(document.author_id),
        created_at=document.created_at,
        updated_at=document.updated_at,
        published_at=document.published_at,
        tags=tags
    )


def _to_document_list_response(document) -> DocumentListResponse:
    """Convert Document model to DocumentListResponse schema."""
    from app.schemas.responses import TagResponse
    
    tags = []
    for doc_tag in document.tags:
        tags.append(TagResponse(
            id=str(doc_tag.tag.id),
            name=doc_tag.tag.name,
            description=doc_tag.tag.description,
            color=doc_tag.tag.color,
            usage_count=doc_tag.tag.usage_count
        ))
    
    return DocumentListResponse(
        id=str(document.id),
        title=document.title,
        slug=document.slug,
        folder_path=document.folder_path,
        status=document.status,
        author_id=str(document.author_id),
        created_at=document.created_at,
        updated_at=document.updated_at,
        published_at=document.published_at,
        tags=tags
    )

@router.get("/{document_id}/revisions", response_model=List[DocumentRevisionListResponse])
async def get_document_revisions(
    document_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100, description="Maximum number of revisions to return"),
    offset: int = Query(0, ge=0, description="Number of revisions to skip"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get revision history for a document.
    
    Returns all revisions for the document in descending order (newest first).
    Only users with read access to the document can view its revisions.
    """
    try:
        service = DocumentService(db)
        revisions = await service.get_document_revisions(
            document_id, current_user, limit=limit, offset=offset
        )
        return [_to_revision_list_response(rev) for rev in revisions]
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=e.message)
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)


@router.get("/{document_id}/revisions/{revision_number}", response_model=DocumentRevisionResponse)
async def get_document_revision(
    document_id: uuid.UUID,
    revision_number: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific revision of a document.
    
    Returns the complete content of the document at the specified revision.
    Only users with read access to the document can view its revisions.
    """
    try:
        service = DocumentService(db)
        revision = await service.get_document_revision(document_id, revision_number, current_user)
        return _to_revision_response(revision)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=e.message)
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)


@router.post("/{document_id}/revisions/{revision_number}/restore", response_model=DocumentResponse)
async def restore_document_revision(
    document_id: uuid.UUID,
    revision_number: int,
    restore_data: DocumentRevisionRestoreRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Restore a document to a previous revision.
    
    Creates a new revision with the content from the specified revision.
    Only the document author or admin can restore revisions.
    """
    try:
        service = DocumentService(db)
        document = await service.restore_document_revision(
            document_id, 
            revision_number, 
            current_user,
            change_summary=restore_data.change_summary
        )
        return _to_document_response(document)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=e.message)
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)


@router.get("/{document_id}/revisions/{revision1}/compare/{revision2}", response_model=DocumentRevisionComparisonResponse)
async def compare_document_revisions(
    document_id: uuid.UUID,
    revision1: int,
    revision2: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Compare two revisions of a document.
    
    Returns detailed comparison data including changes between the two revisions.
    Only users with read access to the document can compare its revisions.
    """
    try:
        service = DocumentService(db)
        comparison = await service.compare_document_revisions(
            document_id, revision1, revision2, current_user
        )
        return DocumentRevisionComparisonResponse(**comparison)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=e.message)
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)


def _to_revision_response(revision) -> DocumentRevisionResponse:
    """Convert DocumentRevision model to DocumentRevisionResponse schema."""
    return DocumentRevisionResponse(
        id=str(revision.id),
        document_id=str(revision.document_id),
        revision_number=revision.revision_number,
        title=revision.title,
        content=revision.content,
        change_summary=revision.change_summary,
        author_id=str(revision.author_id),
        author_username=revision.author.username,
        created_at=revision.created_at
    )


def _to_revision_list_response(revision) -> DocumentRevisionListResponse:
    """Convert DocumentRevision model to DocumentRevisionListResponse schema."""
    return DocumentRevisionListResponse(
        id=str(revision.id),
        document_id=str(revision.document_id),
        revision_number=revision.revision_number,
        title=revision.title,
        change_summary=revision.change_summary,
        author_id=str(revision.author_id),
        author_username=revision.author.username,
        created_at=revision.created_at
    )