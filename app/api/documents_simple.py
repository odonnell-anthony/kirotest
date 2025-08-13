"""
Simple document API endpoints with database operations.
"""
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.database_simple import get_db
from app.services.document_simple import DocumentService
from app.models.document_simple import Document

router = APIRouter()


# Pydantic models for request/response
class DocumentCreate(BaseModel):
    title: str
    content: str
    summary: Optional[str] = None


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = None


class DocumentResponse(BaseModel):
    id: str
    title: str
    content: str
    summary: Optional[str]
    slug: Optional[str]
    is_published: bool
    created_at: str
    updated_at: str


@router.get("/documents", response_model=List[DocumentResponse])
async def list_documents(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """List all documents with pagination."""
    service = DocumentService(db)
    documents = await service.list_documents(limit=limit, offset=offset)
    return [DocumentResponse(**doc.to_dict()) for doc in documents]


@router.get("/documents/search", response_model=List[DocumentResponse])
async def search_documents(
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """Search documents by title and content."""
    service = DocumentService(db)
    documents = await service.search_documents(query=q, limit=limit)
    return [DocumentResponse(**doc.to_dict()) for doc in documents]


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific document by ID."""
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID format")
    
    service = DocumentService(db)
    document = await service.get_document_by_id(doc_uuid)
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return DocumentResponse(**document.to_dict())


@router.get("/documents/slug/{slug}", response_model=DocumentResponse)
async def get_document_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific document by slug."""
    service = DocumentService(db)
    document = await service.get_document_by_slug(slug)
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return DocumentResponse(**document.to_dict())


@router.post("/documents", response_model=DocumentResponse)
async def create_document(
    title: str = Form(...),
    content: str = Form(...),
    summary: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """Create a new document."""
    service = DocumentService(db)
    
    try:
        document = await service.create_document(
            title=title,
            content=content,
            summary=summary
        )
        return DocumentResponse(**document.to_dict())
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error creating document: {str(e)}")


@router.put("/documents/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: str,
    title: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    summary: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """Update an existing document."""
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID format")
    
    service = DocumentService(db)
    document = await service.update_document(
        document_id=doc_uuid,
        title=title,
        content=content,
        summary=summary
    )
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return DocumentResponse(**document.to_dict())


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a document."""
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID format")
    
    service = DocumentService(db)
    success = await service.delete_document(doc_uuid)
    
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return {"message": "Document deleted successfully"}


@router.get("/documents-count")
async def get_document_count(db: AsyncSession = Depends(get_db)):
    """Get total count of documents."""
    service = DocumentService(db)
    count = await service.get_document_count()
    return {"count": count}