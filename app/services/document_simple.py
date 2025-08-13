"""
Simple document service for CRUD operations.
"""
import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.exc import IntegrityError
from app.models.document_simple import Document
import re


class DocumentService:
    """Service for document operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def _generate_slug(self, title: str) -> str:
        """Generate URL-friendly slug from title."""
        # Convert to lowercase and replace spaces/special chars with hyphens
        slug = re.sub(r'[^\w\s-]', '', title.lower())
        slug = re.sub(r'[-\s]+', '-', slug)
        return slug.strip('-')
    
    async def create_document(self, title: str, content: str, summary: str = None) -> Document:
        """Create a new document."""
        # Generate slug from title
        base_slug = self._generate_slug(title)
        slug = base_slug
        
        # Ensure slug is unique
        counter = 1
        while True:
            existing = await self.db.execute(
                select(Document).where(Document.slug == slug)
            )
            if not existing.scalar_one_or_none():
                break
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        # Generate summary if not provided
        if not summary:
            # Take first 200 characters of content as summary
            summary = content[:200] + "..." if len(content) > 200 else content
            # Remove markdown formatting for summary
            summary = re.sub(r'[#*`\[\]()]', '', summary)
        
        document = Document(
            title=title,
            content=content,
            summary=summary,
            slug=slug
        )
        
        self.db.add(document)
        await self.db.commit()
        await self.db.refresh(document)
        
        return document
    
    async def get_document_by_id(self, document_id: uuid.UUID) -> Optional[Document]:
        """Get document by ID."""
        result = await self.db.execute(
            select(Document).where(Document.id == document_id)
        )
        return result.scalar_one_or_none()
    
    async def get_document_by_slug(self, slug: str) -> Optional[Document]:
        """Get document by slug."""
        result = await self.db.execute(
            select(Document).where(Document.slug == slug)
        )
        return result.scalar_one_or_none()
    
    async def list_documents(self, limit: int = 100, offset: int = 0) -> List[Document]:
        """List all documents with pagination."""
        result = await self.db.execute(
            select(Document)
            .where(Document.is_published == True)
            .order_by(Document.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()
    
    async def search_documents(self, query: str, limit: int = 50) -> List[Document]:
        """Search documents by title and content."""
        search_term = f"%{query}%"
        result = await self.db.execute(
            select(Document)
            .where(
                Document.is_published == True,
                or_(
                    Document.title.ilike(search_term),
                    Document.content.ilike(search_term),
                    Document.summary.ilike(search_term)
                )
            )
            .order_by(Document.updated_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
    
    async def update_document(self, document_id: uuid.UUID, title: str = None, content: str = None, summary: str = None) -> Optional[Document]:
        """Update an existing document."""
        document = await self.get_document_by_id(document_id)
        if not document:
            return None
        
        if title is not None:
            document.title = title
            # Update slug if title changed
            new_slug = self._generate_slug(title)
            if new_slug != document.slug:
                # Ensure new slug is unique
                counter = 1
                base_slug = new_slug
                while True:
                    existing = await self.db.execute(
                        select(Document).where(
                            Document.slug == new_slug,
                            Document.id != document_id
                        )
                    )
                    if not existing.scalar_one_or_none():
                        break
                    new_slug = f"{base_slug}-{counter}"
                    counter += 1
                document.slug = new_slug
        
        if content is not None:
            document.content = content
        
        if summary is not None:
            document.summary = summary
        elif content is not None:
            # Auto-generate summary from content
            document.summary = content[:200] + "..." if len(content) > 200 else content
            document.summary = re.sub(r'[#*`\[\]()]', '', document.summary)
        
        await self.db.commit()
        await self.db.refresh(document)
        
        return document
    
    async def delete_document(self, document_id: uuid.UUID) -> bool:
        """Delete a document."""
        document = await self.get_document_by_id(document_id)
        if not document:
            return False
        
        await self.db.delete(document)
        await self.db.commit()
        
        return True
    
    async def get_document_count(self) -> int:
        """Get total count of published documents."""
        result = await self.db.execute(
            select(func.count(Document.id)).where(Document.is_published == True)
        )
        return result.scalar() or 0