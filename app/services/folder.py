"""
Folder service for hierarchical organization management.
"""
import uuid
import logging
from typing import List, Optional, Dict, Any
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.folder import Folder
from app.models.user import User
from app.models.document import Document
from app.schemas.folder import FolderCreate, FolderUpdate, FolderTreeNode
from app.core.exceptions import (
    NotFoundError, PermissionDeniedError, ValidationError,
    DuplicateError, InternalError
)

logger = logging.getLogger(__name__)


class FolderService:
    """Service for managing folder operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_folder(self, folder_data: FolderCreate, user: User) -> Folder:
        """
        Create a new folder.
        
        Args:
            folder_data: Folder creation data
            user: User creating the folder
            
        Returns:
            Created folder
            
        Raises:
            ValidationError: If folder data is invalid
            DuplicateError: If folder path already exists
            InternalError: If creation fails
        """
        try:
            # Check if folder path already exists
            existing = await self._get_folder_by_path(folder_data.path)
            if existing:
                raise DuplicateError(f"Folder path '{folder_data.path}' already exists")
            
            # Validate parent path exists if specified
            if folder_data.parent_path:
                parent = await self._get_folder_by_path(folder_data.parent_path)
                if not parent:
                    raise ValidationError(f"Parent folder '{folder_data.parent_path}' does not exist")
            
            # Create folder
            folder = Folder(
                name=folder_data.name,
                path=folder_data.path,
                parent_path=folder_data.parent_path,
                description=folder_data.description,
                created_by_id=user.id
            )
            
            self.db.add(folder)
            await self.db.commit()
            await self.db.refresh(folder)
            
            logger.info(f"Created folder: {folder.path} by user {user.username}")
            return folder
            
        except (ValidationError, DuplicateError):
            await self.db.rollback()
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating folder: {e}")
            raise InternalError("Failed to create folder")
    
    async def get_folder(self, folder_id: uuid.UUID) -> Folder:
        """
        Get a folder by ID.
        
        Args:
            folder_id: Folder ID
            
        Returns:
            Folder instance
            
        Raises:
            NotFoundError: If folder not found
            InternalError: If retrieval fails
        """
        try:
            stmt = select(Folder).where(Folder.id == folder_id)
            result = await self.db.execute(stmt)
            folder = result.scalar_one_or_none()
            
            if not folder:
                raise NotFoundError(f"Folder with ID {folder_id} not found")
            
            return folder
            
        except NotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error getting folder {folder_id}: {e}")
            raise InternalError("Failed to retrieve folder")
    
    async def list_folders(
        self, 
        parent_path: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Folder]:
        """
        List folders with optional filtering.
        
        Args:
            parent_path: Filter by parent folder path
            limit: Maximum number of folders to return
            offset: Number of folders to skip
            
        Returns:
            List of folders with document counts
            
        Raises:
            InternalError: If listing fails
        """
        try:
            # Build query with document count
            stmt = (
                select(
                    Folder,
                    func.count(Document.id).label('document_count')
                )
                .outerjoin(Document, Document.folder_path == Folder.path)
                .group_by(Folder.id)
                .order_by(Folder.path)
                .limit(limit)
                .offset(offset)
            )
            
            # Add parent path filter if specified
            if parent_path is not None:
                stmt = stmt.where(Folder.parent_path == parent_path)
            
            result = await self.db.execute(stmt)
            rows = result.all()
            
            # Add document count to folder objects
            folders = []
            for folder, doc_count in rows:
                folder.document_count = doc_count
                folders.append(folder)
            
            return folders
            
        except Exception as e:
            logger.error(f"Error listing folders: {e}")
            raise InternalError("Failed to list folders")
    
    async def get_folder_tree(
        self, 
        root_path: Optional[str] = None,
        max_depth: int = 10
    ) -> List[FolderTreeNode]:
        """
        Get folder hierarchy as a tree structure.
        
        Args:
            root_path: Root path for tree (optional)
            max_depth: Maximum tree depth
            
        Returns:
            List of folder tree nodes
            
        Raises:
            InternalError: If tree building fails
        """
        try:
            # Get all folders with document counts
            stmt = (
                select(
                    Folder,
                    func.count(Document.id).label('document_count')
                )
                .outerjoin(Document, Document.folder_path == Folder.path)
                .group_by(Folder.id)
                .order_by(Folder.path)
            )
            
            # Filter by root path if specified
            if root_path:
                stmt = stmt.where(
                    or_(
                        Folder.path == root_path,
                        Folder.path.like(f"{root_path}%")
                    )
                )
            
            result = await self.db.execute(stmt)
            rows = result.all()
            
            # Build folder map
            folder_map = {}
            for folder, doc_count in rows:
                folder_map[folder.path] = {
                    'folder': folder,
                    'document_count': doc_count,
                    'children': []
                }
            
            # Build tree structure
            root_nodes = []
            for path, data in folder_map.items():
                folder = data['folder']
                parent_path = folder.parent_path
                
                if parent_path and parent_path in folder_map:
                    # Add to parent's children
                    folder_map[parent_path]['children'].append(data)
                else:
                    # Root level folder
                    root_nodes.append(data)
            
            # Convert to tree nodes
            def build_tree_node(data: Dict[str, Any], depth: int = 0) -> FolderTreeNode:
                if depth >= max_depth:
                    return None
                
                folder = data['folder']
                children = []
                
                for child_data in data['children']:
                    child_node = build_tree_node(child_data, depth + 1)
                    if child_node:
                        children.append(child_node)
                
                return FolderTreeNode(
                    id=str(folder.id),
                    name=folder.name,
                    path=folder.path,
                    parent_path=folder.parent_path,
                    description=folder.description,
                    created_by_id=str(folder.created_by_id),
                    created_at=folder.created_at.isoformat(),
                    children=children,
                    document_count=data['document_count']
                )
            
            tree = []
            for root_data in root_nodes:
                node = build_tree_node(root_data)
                if node:
                    tree.append(node)
            
            return tree
            
        except Exception as e:
            logger.error(f"Error building folder tree: {e}")
            raise InternalError("Failed to build folder tree")
    
    async def update_folder(
        self, 
        folder_id: uuid.UUID, 
        folder_data: FolderUpdate, 
        user: User
    ) -> Folder:
        """
        Update an existing folder.
        
        Args:
            folder_id: Folder ID
            folder_data: Update data
            user: User performing the update
            
        Returns:
            Updated folder
            
        Raises:
            NotFoundError: If folder not found
            PermissionDeniedError: If user lacks permission
            ValidationError: If update data is invalid
            InternalError: If update fails
        """
        try:
            folder = await self.get_folder(folder_id)
            
            # Check permissions (only creator or admin can update)
            if folder.created_by_id != user.id and user.role != "admin":
                raise PermissionDeniedError("Only folder creator or admin can update folder")
            
            # Update fields
            if folder_data.name is not None:
                folder.name = folder_data.name
            if folder_data.description is not None:
                folder.description = folder_data.description
            
            await self.db.commit()
            await self.db.refresh(folder)
            
            logger.info(f"Updated folder {folder.path} by user {user.username}")
            return folder
            
        except (NotFoundError, PermissionDeniedError, ValidationError):
            await self.db.rollback()
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating folder {folder_id}: {e}")
            raise InternalError("Failed to update folder")
    
    async def delete_folder(
        self, 
        folder_id: uuid.UUID, 
        user: User, 
        force: bool = False
    ) -> None:
        """
        Delete a folder.
        
        Args:
            folder_id: Folder ID
            user: User performing the deletion
            force: Force deletion even if folder contains documents
            
        Raises:
            NotFoundError: If folder not found
            PermissionDeniedError: If user lacks permission
            ValidationError: If folder contains documents and force=False
            InternalError: If deletion fails
        """
        try:
            folder = await self.get_folder(folder_id)
            
            # Check permissions (only creator or admin can delete)
            if folder.created_by_id != user.id and user.role != "admin":
                raise PermissionDeniedError("Only folder creator or admin can delete folder")
            
            # Check for documents in folder if not forcing
            if not force:
                doc_count = await self._get_document_count_in_folder(folder.path)
                if doc_count > 0:
                    raise ValidationError(
                        f"Folder contains {doc_count} documents. Use force=true to delete anyway."
                    )
            
            # Check for child folders
            child_count = await self._get_child_folder_count(folder.path)
            if child_count > 0:
                raise ValidationError(
                    f"Folder contains {child_count} child folders. Delete child folders first."
                )
            
            await self.db.delete(folder)
            await self.db.commit()
            
            logger.info(f"Deleted folder {folder.path} by user {user.username}")
            
        except (NotFoundError, PermissionDeniedError, ValidationError):
            await self.db.rollback()
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deleting folder {folder_id}: {e}")
            raise InternalError("Failed to delete folder")
    
    async def move_folder(
        self, 
        folder_id: uuid.UUID, 
        new_parent_path: Optional[str], 
        user: User
    ) -> Folder:
        """
        Move a folder to a different parent.
        
        Args:
            folder_id: Folder ID
            new_parent_path: New parent folder path (None for root)
            user: User performing the move
            
        Returns:
            Updated folder
            
        Raises:
            NotFoundError: If folder not found
            PermissionDeniedError: If user lacks permission
            ValidationError: If move would create cycle or invalid path
            DuplicateError: If target path already exists
            InternalError: If move fails
        """
        try:
            folder = await self.get_folder(folder_id)
            
            # Check permissions (only creator or admin can move)
            if folder.created_by_id != user.id and user.role != "admin":
                raise PermissionDeniedError("Only folder creator or admin can move folder")
            
            # Validate new parent path exists if specified
            if new_parent_path:
                parent = await self._get_folder_by_path(new_parent_path)
                if not parent:
                    raise ValidationError(f"Parent folder '{new_parent_path}' does not exist")
                
                # Check for circular reference
                if new_parent_path.startswith(folder.path):
                    raise ValidationError("Cannot move folder into its own subtree")
            
            # Calculate new path
            folder_name = folder.name
            if new_parent_path:
                new_path = f"{new_parent_path.rstrip('/')}/{folder_name}/"
            else:
                new_path = f"/{folder_name}/"
            
            # Check if new path already exists
            if new_path != folder.path:
                existing = await self._get_folder_by_path(new_path)
                if existing:
                    raise DuplicateError(f"Folder path '{new_path}' already exists")
            
            # Update folder
            old_path = folder.path
            folder.path = new_path
            folder.parent_path = new_parent_path
            
            # Update all child folders and documents
            await self._update_child_paths(old_path, new_path)
            
            await self.db.commit()
            await self.db.refresh(folder)
            
            logger.info(f"Moved folder from {old_path} to {new_path} by user {user.username}")
            return folder
            
        except (NotFoundError, PermissionDeniedError, ValidationError, DuplicateError):
            await self.db.rollback()
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error moving folder {folder_id}: {e}")
            raise InternalError("Failed to move folder")
    
    async def _get_folder_by_path(self, path: str) -> Optional[Folder]:
        """Get folder by path."""
        stmt = select(Folder).where(Folder.path == path)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def _get_document_count_in_folder(self, folder_path: str) -> int:
        """Get count of documents in folder."""
        stmt = select(func.count(Document.id)).where(Document.folder_path == folder_path)
        result = await self.db.execute(stmt)
        return result.scalar() or 0
    
    async def _get_child_folder_count(self, folder_path: str) -> int:
        """Get count of child folders."""
        stmt = select(func.count(Folder.id)).where(Folder.parent_path == folder_path)
        result = await self.db.execute(stmt)
        return result.scalar() or 0
    
    async def _update_child_paths(self, old_path: str, new_path: str) -> None:
        """Update paths for all child folders and documents."""
        # Update child folders
        stmt = select(Folder).where(Folder.path.like(f"{old_path}%"))
        result = await self.db.execute(stmt)
        child_folders = result.scalars().all()
        
        for child in child_folders:
            if child.path.startswith(old_path):
                child.path = child.path.replace(old_path, new_path, 1)
                if child.parent_path and child.parent_path.startswith(old_path):
                    child.parent_path = child.parent_path.replace(old_path, new_path, 1)
        
        # Update documents in moved folders
        stmt = select(Document).where(Document.folder_path.like(f"{old_path}%"))
        result = await self.db.execute(stmt)
        documents = result.scalars().all()
        
        for doc in documents:
            if doc.folder_path.startswith(old_path):
                doc.folder_path = doc.folder_path.replace(old_path, new_path, 1)    asy
nc def get_all_folders(self) -> List[Folder]:
        """Get all folders for navigation tree building."""
        try:
            result = await self.db.execute(
                select(Folder).order_by(Folder.path)
            )
            folders = result.scalars().all()
            return list(folders)
            
        except Exception as e:
            logger.error(f"Error getting all folders: {e}")
            raise InternalError("Failed to retrieve folders")