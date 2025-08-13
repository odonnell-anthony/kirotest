"""
Document service for content management operations.
"""
import uuid
import re
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, delete, update
from sqlalchemy.orm import selectinload, joinedload

from app.models.document import Document, DocumentStatus, ContentFormat
from app.models.revision import DocumentRevision
from app.models.folder import Folder
from app.models.tag import Tag, DocumentTag
from app.models.user import User
from app.core.exceptions import (
    NotFoundError, PermissionDeniedError, ValidationError, 
    DuplicateError, InternalError
)

logger = logging.getLogger(__name__)


class DocumentService:
    """Service for document CRUD operations and management."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_document(self, doc_data, author: User) -> Document:
        """
        Create a new document with automatic folder creation and tag management.
        
        Args:
            doc_data: Document creation data
            author: User creating the document
            
        Returns:
            Document: Created document data
            
        Raises:
            ValidationError: If document creation fails validation
            DuplicateError: If document with same title exists in folder
            InternalError: If document creation fails
        """
        try:
            # Ensure folder exists (create if necessary)
            await self._ensure_folder_exists(doc_data.folder_path, author)
            
            # Generate slug from title
            slug = self._generate_slug(doc_data.title)
            
            # Check for duplicate title in folder
            existing = await self.db.scalar(
                select(Document).where(
                    and_(
                        Document.folder_path == doc_data.folder_path,
                        Document.slug == slug
                    )
                )
            )
            
            if existing:
                raise DuplicateError(f"Document with title '{doc_data.title}' already exists in folder")
            
            # Create document
            document = Document(
                id=uuid.uuid4(),
                title=doc_data.title,
                slug=slug,
                content=doc_data.content,
                content_type=doc_data.content_type or ContentFormat.MARKDOWN,
                folder_path=doc_data.folder_path,
                status=doc_data.status or DocumentStatus.DRAFT,
                author_id=author.id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            self.db.add(document)
            await self.db.flush()
            
            # Handle tags
            if hasattr(doc_data, 'tags') and doc_data.tags:
                await self._handle_document_tags(document.id, doc_data.tags)
            
            # Create initial revision
            revision = DocumentRevision(
                id=uuid.uuid4(),
                document_id=document.id,
                revision_number=1,
                title=document.title,
                content=document.content,
                author_id=author.id,
                created_at=datetime.utcnow()
            )
            
            self.db.add(revision)
            await self.db.commit()
            
            logger.info(f"Document created: {document.id} by user {author.id}")
            return document
            
            # Generate slug from title
            slug = self._generate_slug(doc_data.title)
            
            # Check for duplicate slug in the same folder
            await self._check_duplicate_slug(doc_data.folder_path, slug)
            
            # Create document
            document = Document(
                title=doc_data.title,
                slug=slug,
                content=doc_data.content,
                content_type=doc_data.content_type,
                folder_path=doc_data.folder_path,
                status=doc_data.status,
                author_id=author.id,
                published_at=datetime.utcnow() if doc_data.status == DocumentStatus.PUBLISHED else None
            )
            
            self.db.add(document)
            await self.db.flush()  # Get the document ID
            
            # Handle tags
            if hasattr(doc_data, 'tags') and doc_data.tags:
                await self._associate_tags(document.id, doc_data.tags)
            
            await self.db.commit()
            
            # Reload document with relationships
            result = await self.db.execute(
                select(Document)
                .options(
                    selectinload(Document.tags).selectinload(DocumentTag.tag)
                )
                .where(Document.id == document.id)
            )
            created_document = result.scalar_one()
            
            logger.info(f"Document created: {created_document.id} by user {author.id}")
            return created_document
            
        except (ValidationError, DuplicateError):
            await self.db.rollback()
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating document: {e}")
            raise InternalError("Failed to create document")
    
    async def get_document(self, document_id: uuid.UUID, user: User) -> Document:
        """
        Get a document by ID with visibility controls.
        
        Args:
            document_id: Document ID
            user: User requesting the document
            
        Returns:
            Document: Document data
            
        Raises:
            NotFoundError: If document not found or access denied
        """
        try:
            # Build query with visibility controls
            query = (
                select(Document)
                .options(
                    selectinload(Document.tags).selectinload(DocumentTag.tag)
                )
                .where(Document.id == document_id)
            )
            
            # Apply visibility controls
            if user.role.value != "admin":
                # Normal users can see:
                # 1. Published documents
                # 2. Their own draft documents
                query = query.where(
                    or_(
                        Document.status == DocumentStatus.PUBLISHED,
                        and_(
                            Document.status == DocumentStatus.DRAFT,
                            Document.author_id == user.id
                        )
                    )
                )
            
            result = await self.db.execute(query)
            document = result.scalar_one_or_none()
            
            if not document:
                raise NotFoundError("Document not found")
            
            return document
            
        except NotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error getting document {document_id}: {e}")
            raise InternalError("Failed to retrieve document")
    
    async def update_document(
        self, 
        document_id: uuid.UUID, 
        doc_data, 
        user: User,
        change_summary: Optional[str] = None
    ) -> Document:
        """
        Update an existing document with validation, tag management, and automatic revision creation.
        
        Args:
            document_id: Document ID to update
            doc_data: Update data
            user: User performing the update
            change_summary: Optional summary of changes made
            
        Returns:
            Document: Updated document data
            
        Raises:
            NotFoundError: If document not found
            PermissionDeniedError: If access denied
        """
        try:
            # Get existing document
            result = await self.db.execute(
                select(Document)
                .options(
                    selectinload(Document.tags).selectinload(DocumentTag.tag)
                )
                .where(Document.id == document_id)
            )
            document = result.scalar_one_or_none()
            
            if not document:
                raise NotFoundError("Document not found")
            
            # Check permissions (only author or admin can edit)
            if user.role.value != "admin" and document.author_id != user.id:
                raise PermissionDeniedError("Not authorized to edit this document")
            
            # Create revision before making changes
            await self._create_revision(document, user, change_summary)
            
            # Update fields
            update_data = {}
            
            if hasattr(doc_data, 'title') and doc_data.title is not None:
                # Generate new slug if title changed
                if doc_data.title != document.title:
                    new_slug = self._generate_slug(doc_data.title)
                    folder_path = getattr(doc_data, 'folder_path', None) or document.folder_path
                    await self._check_duplicate_slug(folder_path, new_slug, exclude_id=document_id)
                    update_data['slug'] = new_slug
                update_data['title'] = doc_data.title
            
            if hasattr(doc_data, 'content') and doc_data.content is not None:
                update_data['content'] = doc_data.content
            
            if hasattr(doc_data, 'content_type') and doc_data.content_type is not None:
                update_data['content_type'] = doc_data.content_type
            
            if hasattr(doc_data, 'folder_path') and doc_data.folder_path is not None:
                # Ensure new folder exists
                await self._ensure_folder_exists(doc_data.folder_path, user)
                # Check slug uniqueness in new folder
                slug = update_data.get('slug', document.slug)
                await self._check_duplicate_slug(doc_data.folder_path, slug, exclude_id=document_id)
                update_data['folder_path'] = doc_data.folder_path
            
            if hasattr(doc_data, 'status') and doc_data.status is not None:
                update_data['status'] = doc_data.status
                # Set published_at when publishing
                if (doc_data.status == DocumentStatus.PUBLISHED and 
                    document.status != DocumentStatus.PUBLISHED):
                    update_data['published_at'] = datetime.utcnow()
            
            # Apply updates
            if update_data:
                update_data['updated_at'] = datetime.utcnow()
                await self.db.execute(
                    update(Document)
                    .where(Document.id == document_id)
                    .values(**update_data)
                )
            
            # Handle tag updates
            if hasattr(doc_data, 'tags') and doc_data.tags is not None:
                # Get existing tag IDs for usage count updates
                existing_tags_result = await self.db.execute(
                    select(DocumentTag.tag_id).where(DocumentTag.document_id == document_id)
                )
                existing_tag_ids = [row[0] for row in existing_tags_result.fetchall()]
                
                # Remove existing tags
                await self.db.execute(
                    delete(DocumentTag).where(DocumentTag.document_id == document_id)
                )
                
                # Update usage counts for removed tags
                if existing_tag_ids:
                    await self._update_tag_usage_counts(existing_tag_ids)
                
                # Add new tags
                if doc_data.tags:
                    await self._associate_tags(document_id, doc_data.tags)
            
            await self.db.commit()
            
            # Reload updated document
            result = await self.db.execute(
                select(Document)
                .options(
                    selectinload(Document.tags).selectinload(DocumentTag.tag)
                )
                .where(Document.id == document_id)
            )
            updated_document = result.scalar_one()
            
            logger.info(f"Document updated: {document_id} by user {user.id}")
            return updated_document
            
        except (NotFoundError, PermissionDeniedError, ValidationError, DuplicateError):
            await self.db.rollback()
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating document {document_id}: {e}")
            raise InternalError("Failed to update document")
    
    async def delete_document(self, document_id: uuid.UUID, user: User) -> None:
        """
        Delete a document (only author or admin can delete).
        
        Args:
            document_id: Document ID to delete
            user: User performing the deletion
            
        Raises:
            NotFoundError: If document not found
            PermissionDeniedError: If access denied
        """
        try:
            # Get document
            result = await self.db.execute(
                select(Document).where(Document.id == document_id)
            )
            document = result.scalar_one_or_none()
            
            if not document:
                raise NotFoundError("Document not found")
            
            # Check permissions
            if user.role.value != "admin" and document.author_id != user.id:
                raise PermissionDeniedError("Not authorized to delete this document")
            
            # Get tag IDs for usage count updates before deletion
            tag_ids_result = await self.db.execute(
                select(DocumentTag.tag_id).where(DocumentTag.document_id == document_id)
            )
            tag_ids_to_update = [row[0] for row in tag_ids_result.fetchall()]
            
            # Delete document (cascading will handle related records)
            await self.db.execute(
                delete(Document).where(Document.id == document_id)
            )
            
            # Update usage counts for affected tags
            if tag_ids_to_update:
                await self._update_tag_usage_counts(tag_ids_to_update)
            
            await self.db.commit()
            logger.info(f"Document deleted: {document_id} by user {user.id}")
            
        except (NotFoundError, PermissionDeniedError):
            await self.db.rollback()
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting document {document_id}: {e}")
            raise InternalError("Failed to delete document")
    
    async def move_document(
        self, 
        document_id: uuid.UUID, 
        new_folder_path: str, 
        user: User
    ) -> Document:
        """
        Move a document to a different folder.
        
        Args:
            document_id: Document ID to move
            new_folder_path: New folder path
            user: User performing the move
            
        Returns:
            Document: Updated document data
            
        Raises:
            NotFoundError: If document not found
            PermissionDeniedError: If access denied
        """
        try:
            # Get document
            result = await self.db.execute(
                select(Document)
                .options(
                    selectinload(Document.tags).selectinload(DocumentTag.tag)
                )
                .where(Document.id == document_id)
            )
            document = result.scalar_one_or_none()
            
            if not document:
                raise NotFoundError("Document not found")
            
            # Check permissions
            if user.role.value != "admin" and document.author_id != user.id:
                raise PermissionDeniedError("Not authorized to move this document")
            
            # Ensure target folder exists
            await self._ensure_folder_exists(new_folder_path, user)
            
            # Check slug uniqueness in target folder
            await self._check_duplicate_slug(
                new_folder_path, 
                document.slug, 
                exclude_id=document_id
            )
            
            # Update folder path
            await self.db.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(
                    folder_path=new_folder_path,
                    updated_at=datetime.utcnow()
                )
            )
            
            await self.db.commit()
            
            # Reload document
            result = await self.db.execute(
                select(Document)
                .options(
                    selectinload(Document.tags).selectinload(DocumentTag.tag)
                )
                .where(Document.id == document_id)
            )
            moved_document = result.scalar_one()
            
            logger.info(f"Document moved: {document_id} to {new_folder_path} by user {user.id}")
            return moved_document
            
        except (NotFoundError, PermissionDeniedError, ValidationError, DuplicateError):
            await self.db.rollback()
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error moving document {document_id}: {e}")
            raise InternalError("Failed to move document")
    
    async def list_documents(
        self, 
        user: User,
        folder_path: Optional[str] = None,
        status: Optional[DocumentStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Document]:
        """
        List documents with filtering and pagination.
        
        Args:
            user: User requesting the list
            folder_path: Optional folder path filter
            status: Optional status filter
            limit: Maximum number of documents to return
            offset: Number of documents to skip
            
        Returns:
            List[Document]: List of documents
        """
        try:
            query = (
                select(Document)
                .options(
                    selectinload(Document.tags).selectinload(DocumentTag.tag)
                )
                .order_by(Document.updated_at.desc())
            )
            
            # Apply visibility controls
            if user.role.value != "admin":
                query = query.where(
                    or_(
                        Document.status == DocumentStatus.PUBLISHED,
                        and_(
                            Document.status == DocumentStatus.DRAFT,
                            Document.author_id == user.id
                        )
                    )
                )
            
            # Apply filters
            if folder_path:
                query = query.where(Document.folder_path == folder_path)
            
            if status:
                query = query.where(Document.status == status)
            
            # Apply pagination
            query = query.limit(limit).offset(offset)
            
            result = await self.db.execute(query)
            documents = result.scalars().all()
            
            return list(documents)
            
        except Exception as e:
            logger.error(f"Error listing documents: {e}")
            raise InternalError("Failed to retrieve documents")
    
    # Private helper methods
    
    async def _ensure_folder_exists(self, folder_path: str, user: User) -> None:
        """Ensure folder hierarchy exists, creating folders as needed."""
        if folder_path == "/":
            return  # Root folder always exists
        
        # Parse folder path into components
        path_parts = [part for part in folder_path.strip('/').split('/') if part]
        
        current_path = "/"
        for part in path_parts:
            current_path = current_path.rstrip('/') + '/' + part + '/'
            
            # Check if folder exists
            result = await self.db.execute(
                select(Folder).where(Folder.path == current_path)
            )
            existing_folder = result.scalar_one_or_none()
            
            if not existing_folder:
                # Create folder
                parent_path = '/'.join(current_path.strip('/').split('/')[:-1])
                if parent_path and parent_path != current_path.strip('/'):
                    parent_path = '/' + parent_path + '/'
                else:
                    parent_path = None
                
                folder = Folder(
                    name=part,
                    path=current_path,
                    parent_path=parent_path,
                    created_by_id=user.id
                )
                self.db.add(folder)
                logger.info(f"Created folder: {current_path}")
    
    def _generate_slug(self, title: str) -> str:
        """Generate URL-friendly slug from title."""
        # Convert to lowercase and replace spaces/special chars with hyphens
        slug = re.sub(r'[^\w\s-]', '', title.lower())
        slug = re.sub(r'[-\s]+', '-', slug)
        return slug.strip('-')
    
    async def _check_duplicate_slug(
        self, 
        folder_path: str, 
        slug: str, 
        exclude_id: Optional[uuid.UUID] = None
    ) -> None:
        """Check for duplicate slug in the same folder."""
        query = select(Document).where(
            and_(
                Document.folder_path == folder_path,
                Document.slug == slug
            )
        )
        
        if exclude_id:
            query = query.where(Document.id != exclude_id)
        
        result = await self.db.execute(query)
        existing = result.scalar_one_or_none()
        
        if existing:
            raise DuplicateError(f"A document with this title already exists in folder {folder_path}")
    
    async def _associate_tags(self, document_id: uuid.UUID, tag_names: List[str]) -> None:
        """Associate tags with a document, creating tags if they don't exist."""
        tag_ids_to_update = []
        
        for tag_name in tag_names:
            # Normalize tag name
            normalized_name = tag_name.strip().lower()
            
            # Get or create tag
            result = await self.db.execute(
                select(Tag).where(Tag.name == normalized_name)
            )
            tag = result.scalar_one_or_none()
            
            if not tag:
                tag = Tag(name=normalized_name, usage_count=0)
                self.db.add(tag)
                await self.db.flush()  # Get tag ID
            
            # Create document-tag association
            doc_tag = DocumentTag(
                document_id=document_id,
                tag_id=tag.id
            )
            self.db.add(doc_tag)
            tag_ids_to_update.append(tag.id)
        
        # Update usage counts for all affected tags
        if tag_ids_to_update:
            await self._update_tag_usage_counts(tag_ids_to_update)
    
    async def _update_tag_usage_counts(self, tag_ids: List[uuid.UUID]) -> None:
        """Update usage counts for specific tags."""
        for tag_id in tag_ids:
            # Count current usage
            count_result = await self.db.execute(
                select(func.count(DocumentTag.document_id))
                .where(DocumentTag.tag_id == tag_id)
            )
            usage_count = count_result.scalar() or 0
            
            # Update the tag's usage count
            await self.db.execute(
                update(Tag)
                .where(Tag.id == tag_id)
                .values(usage_count=usage_count)
            )
    
    async def _create_revision(
        self, 
        document: Document, 
        user: User, 
        change_summary: Optional[str] = None
    ) -> DocumentRevision:
        """Create a revision snapshot of the current document state."""
        try:
            # Get the next revision number
            result = await self.db.execute(
                select(func.max(DocumentRevision.revision_number))
                .where(DocumentRevision.document_id == document.id)
            )
            max_revision = result.scalar() or 0
            next_revision = max_revision + 1
            
            # Create revision
            revision = DocumentRevision(
                document_id=document.id,
                revision_number=next_revision,
                title=document.title,
                content=document.content,
                change_summary=change_summary,
                author_id=user.id
            )
            
            self.db.add(revision)
            await self.db.flush()  # Get revision ID
            
            logger.info(f"Created revision {next_revision} for document {document.id}")
            return revision
            
        except Exception as e:
            logger.error(f"Error creating revision for document {document.id}: {e}")
            raise InternalError("Failed to create document revision")
    
    async def get_document_revisions(
        self, 
        document_id: uuid.UUID, 
        user: User,
        limit: int = 50,
        offset: int = 0
    ) -> List[DocumentRevision]:
        """
        Get revision history for a document.
        
        Args:
            document_id: Document ID
            user: User requesting revisions
            limit: Maximum number of revisions to return
            offset: Number of revisions to skip
            
        Returns:
            List[DocumentRevision]: List of document revisions
            
        Raises:
            NotFoundError: If document not found
            PermissionDeniedError: If access denied
        """
        try:
            # First check if document exists and user has access
            await self.get_document(document_id, user)
            
            # Get revisions
            result = await self.db.execute(
                select(DocumentRevision)
                .options(joinedload(DocumentRevision.author))
                .where(DocumentRevision.document_id == document_id)
                .order_by(DocumentRevision.revision_number.desc())
                .limit(limit)
                .offset(offset)
            )
            revisions = result.scalars().all()
            
            return list(revisions)
            
        except (NotFoundError, PermissionDeniedError):
            raise
        except Exception as e:
            logger.error(f"Error getting revisions for document {document_id}: {e}")
            raise InternalError("Failed to retrieve document revisions")
    
    async def get_document_revision(
        self, 
        document_id: uuid.UUID, 
        revision_number: int, 
        user: User
    ) -> DocumentRevision:
        """
        Get a specific revision of a document.
        
        Args:
            document_id: Document ID
            revision_number: Revision number to retrieve
            user: User requesting the revision
            
        Returns:
            DocumentRevision: Document revision data
            
        Raises:
            NotFoundError: If document or revision not found
            PermissionDeniedError: If access denied
        """
        try:
            # First check if document exists and user has access
            await self.get_document(document_id, user)
            
            # Get specific revision
            result = await self.db.execute(
                select(DocumentRevision)
                .options(joinedload(DocumentRevision.author))
                .where(
                    and_(
                        DocumentRevision.document_id == document_id,
                        DocumentRevision.revision_number == revision_number
                    )
                )
            )
            revision = result.scalar_one_or_none()
            
            if not revision:
                raise NotFoundError(f"Revision {revision_number} not found for document")
            
            return revision
            
        except (NotFoundError, PermissionDeniedError):
            raise
        except Exception as e:
            logger.error(f"Error getting revision {revision_number} for document {document_id}: {e}")
            raise InternalError("Failed to retrieve document revision")
    
    async def restore_document_revision(
        self, 
        document_id: uuid.UUID, 
        revision_number: int, 
        user: User,
        change_summary: Optional[str] = None
    ) -> Document:
        """
        Restore a document to a previous revision.
        
        Args:
            document_id: Document ID
            revision_number: Revision number to restore
            user: User performing the restoration
            change_summary: Optional summary for the restoration
            
        Returns:
            Document: Updated document data
            
        Raises:
            NotFoundError: If document or revision not found
            PermissionDeniedError: If access denied
        """
        try:
            # Get the revision to restore
            revision = await self.get_document_revision(document_id, revision_number, user)
            
            # Get current document
            result = await self.db.execute(
                select(Document)
                .options(
                    selectinload(Document.tags).selectinload(DocumentTag.tag)
                )
                .where(Document.id == document_id)
            )
            document = result.scalar_one_or_none()
            
            if not document:
                raise NotFoundError("Document not found")
            
            # Check permissions (only author or admin can restore)
            if user.role.value != "admin" and document.author_id != user.id:
                raise PermissionDeniedError("Not authorized to restore this document")
            
            # Create revision of current state before restoration
            restore_summary = change_summary or f"Restored to revision {revision_number}"
            await self._create_revision(document, user, restore_summary)
            
            # Restore document content
            await self.db.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(
                    title=revision.title,
                    content=revision.content,
                    updated_at=datetime.utcnow()
                )
            )
            
            await self.db.commit()
            
            # Reload updated document
            result = await self.db.execute(
                select(Document)
                .options(
                    selectinload(Document.tags).selectinload(DocumentTag.tag)
                )
                .where(Document.id == document_id)
            )
            restored_document = result.scalar_one()
            
            logger.info(f"Document {document_id} restored to revision {revision_number} by user {user.id}")
            return restored_document
            
        except (NotFoundError, PermissionDeniedError):
            await self.db.rollback()
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error restoring document {document_id} to revision {revision_number}: {e}")
            raise InternalError("Failed to restore document revision")
    
    async def compare_document_revisions(
        self, 
        document_id: uuid.UUID, 
        revision1: int, 
        revision2: int, 
        user: User
    ) -> Dict[str, Any]:
        """
        Compare two revisions of a document.
        
        Args:
            document_id: Document ID
            revision1: First revision number
            revision2: Second revision number
            user: User requesting the comparison
            
        Returns:
            Dict containing comparison data
            
        Raises:
            NotFoundError: If document or revisions not found
            PermissionDeniedError: If access denied
        """
        try:
            # Get both revisions
            rev1 = await self.get_document_revision(document_id, revision1, user)
            rev2 = await self.get_document_revision(document_id, revision2, user)
            
            # Basic comparison data
            comparison = {
                "document_id": str(document_id),
                "revision1": {
                    "number": rev1.revision_number,
                    "title": rev1.title,
                    "content": rev1.content,
                    "author_id": str(rev1.author_id),
                    "author_username": rev1.author.username,
                    "created_at": rev1.created_at,
                    "change_summary": rev1.change_summary
                },
                "revision2": {
                    "number": rev2.revision_number,
                    "title": rev2.title,
                    "content": rev2.content,
                    "author_id": str(rev2.author_id),
                    "author_username": rev2.author.username,
                    "created_at": rev2.created_at,
                    "change_summary": rev2.change_summary
                },
                "changes": {
                    "title_changed": rev1.title != rev2.title,
                    "content_changed": rev1.content != rev2.content,
                    "title_diff": {
                        "old": rev1.title,
                        "new": rev2.title
                    } if rev1.title != rev2.title else None,
                    # For content diff, we provide the raw content
                    # Client-side can implement more sophisticated diff algorithms
                    "content_diff": {
                        "old": rev1.content,
                        "new": rev2.content
                    } if rev1.content != rev2.content else None
                }
            }
            
            return comparison
            
        except (NotFoundError, PermissionDeniedError):
            raise
        except Exception as e:
            logger.error(f"Error comparing revisions {revision1} and {revision2} for document {document_id}: {e}")
            raise InternalError("Failed to compare document revisions")    as
ync def get_all_documents_summary(self) -> List[Document]:
        """Get a summary of all published documents for navigation."""
        try:
            result = await self.db.execute(
                select(Document)
                .where(Document.status == DocumentStatus.PUBLISHED)
                .order_by(Document.folder_path, Document.title)
            )
            documents = result.scalars().all()
            return list(documents)
            
        except Exception as e:
            logger.error(f"Error getting documents summary: {e}")
            raise InternalError("Failed to retrieve documents summary")
    
    async def get_document_by_path(self, path: str) -> Optional[Document]:
        """Get a document by its path (slug)."""
        try:
            # Extract slug from path (remove leading slash)
            slug = path.lstrip('/')
            
            result = await self.db.execute(
                select(Document)
                .options(
                    selectinload(Document.tags).selectinload(DocumentTag.tag),
                    joinedload(Document.author)
                )
                .where(Document.slug == slug)
            )
            document = result.scalar_one_or_none()
            return document
            
        except Exception as e:
            logger.error(f"Error getting document by path {path}: {e}")
            raise InternalError("Failed to retrieve document")
    
    async def _handle_document_tags(self, document_id: uuid.UUID, tag_names: List[str]) -> None:
        """Handle tag associations for a document."""
        if not tag_names:
            return
        
        await self._associate_tags(document_id, tag_names)