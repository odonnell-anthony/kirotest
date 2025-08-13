"""
Folder management API endpoints.
"""
import uuid
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.services.folder import FolderService
from app.schemas.folder import (
    FolderCreate, FolderUpdate, FolderMoveRequest,
    FolderTreeNode, FolderListResponse
)
from app.core.exceptions import (
    NotFoundError, PermissionDeniedError, ValidationError,
    DuplicateError, InternalError
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/folders", tags=["folders"])


@router.post("/", response_model=FolderListResponse, status_code=status.HTTP_201_CREATED)
async def create_folder(
    folder_data: FolderCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new folder.
    
    - **name**: Folder name (required, alphanumeric with hyphens/underscores)
    - **path**: Full folder path (required)
    - **parent_path**: Parent folder path (optional)
    - **description**: Folder description (optional)
    """
    try:
        service = FolderService(db)
        folder = await service.create_folder(folder_data, current_user)
        return _to_folder_response(folder)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
    except DuplicateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)


@router.get("/", response_model=List[FolderListResponse])
async def list_folders(
    parent_path: Optional[str] = Query(None, description="Filter by parent folder path"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of folders to return"),
    offset: int = Query(0, ge=0, description="Number of folders to skip"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List folders with optional filtering and pagination.
    
    - **parent_path**: Filter by parent folder path
    - **limit**: Maximum number of folders to return (1-1000)
    - **offset**: Number of folders to skip for pagination
    """
    try:
        service = FolderService(db)
        folders = await service.list_folders(
            parent_path=parent_path,
            limit=limit,
            offset=offset
        )
        return [_to_folder_response(folder) for folder in folders]
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)


@router.get("/tree", response_model=List[FolderTreeNode])
async def get_folder_tree(
    root_path: Optional[str] = Query(None, description="Root path for tree (default: all folders)"),
    max_depth: int = Query(10, ge=1, le=20, description="Maximum tree depth"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get folder hierarchy as a tree structure.
    
    - **root_path**: Root path for tree (optional, defaults to all folders)
    - **max_depth**: Maximum tree depth (1-20)
    
    Returns folders organized in a hierarchical tree structure with document counts.
    """
    try:
        service = FolderService(db)
        tree = await service.get_folder_tree(root_path=root_path, max_depth=max_depth)
        return tree
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)


@router.get("/{folder_id}", response_model=FolderListResponse)
async def get_folder(
    folder_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific folder by ID.
    
    - **folder_id**: UUID of the folder to retrieve
    """
    try:
        service = FolderService(db)
        folder = await service.get_folder(folder_id)
        return _to_folder_response(folder)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)


@router.put("/{folder_id}", response_model=FolderListResponse)
async def update_folder(
    folder_id: uuid.UUID,
    folder_data: FolderUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update an existing folder.
    
    - **folder_id**: UUID of the folder to update
    - **name**: New folder name (optional)
    - **description**: New folder description (optional)
    
    Only the folder creator or admin can update a folder.
    """
    try:
        service = FolderService(db)
        folder = await service.update_folder(folder_id, folder_data, current_user)
        return _to_folder_response(folder)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=e.message)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: uuid.UUID,
    force: bool = Query(False, description="Force deletion even if folder contains documents"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a folder.
    
    - **folder_id**: UUID of the folder to delete
    - **force**: Force deletion even if folder contains documents
    
    Only the folder creator or admin can delete a folder.
    By default, folders with documents cannot be deleted unless force=true.
    """
    try:
        service = FolderService(db)
        await service.delete_folder(folder_id, current_user, force=force)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message)
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=e.message)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
    except InternalError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=e.message)


@router.post("/{folder_id}/move", response_model=FolderListResponse)
async def move_folder(
    folder_id: uuid.UUID,
    move_data: FolderMoveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Move a folder to a different parent.
    
    - **folder_id**: UUID of the folder to move
    - **new_parent_path**: New parent folder path (null for root)
    
    Only the folder creator or admin can move a folder.
    """
    try:
        service = FolderService(db)
        folder = await service.move_folder(folder_id, move_data.new_parent_path, current_user)
        return _to_folder_response(folder)
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


def _to_folder_response(folder) -> FolderListResponse:
    """Convert Folder model to FolderListResponse schema."""
    return FolderListResponse(
        id=str(folder.id),
        name=folder.name,
        path=folder.path,
        parent_path=folder.parent_path,
        description=folder.description,
        created_by_id=str(folder.created_by),
        created_at=folder.created_at.isoformat(),
        document_count=getattr(folder, 'document_count', 0)
    )