"""
File management API endpoints with security scanning.
"""
import logging
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File as FastAPIFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.rate_limit import upload_rate_limit
from app.models.user import User
from app.services.file import FileService, FileUploadError, MalwareDetectedError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/files", tags=["files"])


class FileUploadResponse(BaseModel):
    """File upload response model."""
    id: str
    filename: str
    original_filename: str
    file_size: int
    mime_type: str
    checksum: str
    created_at: str
    message: str


class ImagePasteRequest(BaseModel):
    """Image paste request model."""
    image_data: str
    folder_path: str = "/"
    document_id: Optional[str] = None


class FileInfoResponse(BaseModel):
    """File information response model."""
    id: str
    filename: str
    original_filename: str
    file_path: str
    mime_type: str
    file_size: int
    checksum: str
    uploaded_by: str
    document_id: Optional[str]
    created_at: str


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str


async def get_file_service(db: AsyncSession = Depends(get_db)) -> FileService:
    """Dependency to get file service."""
    from app.services.permission import PermissionService
    permission_service = PermissionService(db)
    return FileService(db, permission_service=permission_service)


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    request: Request,
    file: UploadFile = FastAPIFile(...),
    folder_path: str = "/",
    document_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    file_service: FileService = Depends(get_file_service),
    _rate_limit: dict = Depends(upload_rate_limit)
):
    """
    Upload a file with security scanning.
    
    Args:
        request: FastAPI request object
        file: File to upload
        folder_path: Destination folder path
        document_id: Optional associated document ID
        current_user: Current authenticated user
        file_service: File service
        _rate_limit: Rate limit check
        
    Returns:
        FileUploadResponse: Upload result
        
    Raises:
        HTTPException: If upload fails
    """
    try:
        # Get client IP
        client_ip = None
        if request.client:
            client_ip = request.client.host
        elif "x-forwarded-for" in request.headers:
            client_ip = request.headers["x-forwarded-for"].split(",")[0].strip()
        elif "x-real-ip" in request.headers:
            client_ip = request.headers["x-real-ip"]
        
        # Parse document ID if provided
        doc_uuid = None
        if document_id:
            try:
                doc_uuid = uuid.UUID(document_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid document ID format"
                )
        
        # Upload file
        file_record = await file_service.upload_file(
            file=file,
            user=current_user,
            folder_path=folder_path,
            document_id=doc_uuid,
            ip_address=client_ip
        )
        
        logger.info(f"File uploaded successfully: {file.filename} by {current_user.username}")
        
        return FileUploadResponse(
            id=str(file_record.id),
            filename=file_record.filename,
            original_filename=file_record.original_filename,
            file_size=file_record.file_size,
            mime_type=file_record.mime_type,
            checksum=file_record.checksum,
            created_at=file_record.created_at.isoformat(),
            message="File uploaded successfully"
        )
        
    except MalwareDetectedError as e:
        logger.warning(f"Malware detected in upload by {current_user.username}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Security threat detected: {str(e)}"
        )
    except FileUploadError as e:
        logger.warning(f"File upload error for {current_user.username}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error during file upload: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="File upload failed"
        )


@router.get("/{file_id}", response_model=FileInfoResponse)
async def get_file_info(
    file_id: str,
    current_user: User = Depends(get_current_user),
    file_service: FileService = Depends(get_file_service)
):
    """
    Get file information.
    
    Args:
        file_id: File ID
        current_user: Current authenticated user
        file_service: File service
        
    Returns:
        FileInfoResponse: File information
        
    Raises:
        HTTPException: If file not found or access denied
    """
    try:
        file_uuid = uuid.UUID(file_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file ID format"
        )
    
    try:
        file_record = await file_service.get_file(
            file_id=file_uuid,
            user=current_user
        )
        
        if not file_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found or access denied"
            )
        
        return FileInfoResponse(
            id=str(file_record.id),
            filename=file_record.filename,
            original_filename=file_record.original_filename,
            file_path=file_record.file_path,
            mime_type=file_record.mime_type,
            file_size=file_record.file_size,
            checksum=file_record.checksum,
            uploaded_by=str(file_record.uploaded_by),
            document_id=str(file_record.document_id) if file_record.document_id else None,
            created_at=file_record.created_at.isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting file info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get file information"
        )


@router.get("/{file_id}/download")
async def download_file(
    request: Request,
    file_id: str,
    current_user: User = Depends(get_current_user),
    file_service: FileService = Depends(get_file_service)
):
    """
    Download a file.
    
    Args:
        request: FastAPI request object
        file_id: File ID
        current_user: Current authenticated user
        file_service: File service
        
    Returns:
        FileResponse: File download response
        
    Raises:
        HTTPException: If file not found or access denied
    """
    try:
        file_uuid = uuid.UUID(file_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file ID format"
        )
    
    try:
        # Get client IP
        client_ip = None
        if request.client:
            client_ip = request.client.host
        elif "x-forwarded-for" in request.headers:
            client_ip = request.headers["x-forwarded-for"].split(",")[0].strip()
        elif "x-real-ip" in request.headers:
            client_ip = request.headers["x-real-ip"]
        
        file_record = await file_service.get_file(
            file_id=file_uuid,
            user=current_user,
            ip_address=client_ip
        )
        
        if not file_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found or access denied"
            )
        
        # Get file path
        file_path = file_service.get_file_path(file_record)
        
        if not file_path.exists():
            logger.error(f"File not found on disk: {file_path}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found on disk"
            )
        
        return FileResponse(
            path=str(file_path),
            filename=file_record.original_filename,
            media_type=file_record.mime_type
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to download file"
        )


@router.delete("/{file_id}", response_model=MessageResponse)
async def delete_file(
    request: Request,
    file_id: str,
    current_user: User = Depends(get_current_user),
    file_service: FileService = Depends(get_file_service)
):
    """
    Delete a file.
    
    Args:
        request: FastAPI request object
        file_id: File ID
        current_user: Current authenticated user
        file_service: File service
        
    Returns:
        MessageResponse: Deletion confirmation
        
    Raises:
        HTTPException: If file not found or access denied
    """
    try:
        file_uuid = uuid.UUID(file_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file ID format"
        )
    
    try:
        # Get client IP
        client_ip = None
        if request.client:
            client_ip = request.client.host
        elif "x-forwarded-for" in request.headers:
            client_ip = request.headers["x-forwarded-for"].split(",")[0].strip()
        elif "x-real-ip" in request.headers:
            client_ip = request.headers["x-real-ip"]
        
        success = await file_service.delete_file(
            file_id=file_uuid,
            user=current_user,
            ip_address=client_ip
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found or access denied"
            )
        
        return MessageResponse(message="File deleted successfully")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete file"
        )


@router.put("/{file_id}/move", response_model=FileInfoResponse)
async def move_file(
    request: Request,
    file_id: str,
    new_folder_path: str,
    current_user: User = Depends(get_current_user),
    file_service: FileService = Depends(get_file_service)
):
    """
    Move a file to a new folder.
    
    Args:
        request: FastAPI request object
        file_id: File ID
        new_folder_path: New folder path
        current_user: Current authenticated user
        file_service: File service
        
    Returns:
        FileInfoResponse: Updated file information
        
    Raises:
        HTTPException: If file not found or access denied
    """
    try:
        file_uuid = uuid.UUID(file_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file ID format"
        )
    
    try:
        # Get client IP
        client_ip = None
        if request.client:
            client_ip = request.client.host
        elif "x-forwarded-for" in request.headers:
            client_ip = request.headers["x-forwarded-for"].split(",")[0].strip()
        elif "x-real-ip" in request.headers:
            client_ip = request.headers["x-real-ip"]
        
        file_record = await file_service.move_file(
            file_id=file_uuid,
            new_folder_path=new_folder_path,
            user=current_user,
            ip_address=client_ip
        )
        
        if not file_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found or access denied"
            )
        
        return FileInfoResponse(
            id=str(file_record.id),
            filename=file_record.filename,
            original_filename=file_record.original_filename,
            file_path=file_record.file_path,
            mime_type=file_record.mime_type,
            file_size=file_record.file_size,
            checksum=file_record.checksum,
            uploaded_by=str(file_record.uploaded_by),
            document_id=str(file_record.document_id) if file_record.document_id else None,
            created_at=file_record.created_at.isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error moving file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to move file"
        )


@router.post("/paste-image", response_model=FileUploadResponse)
async def paste_image(
    request: Request,
    image_request: ImagePasteRequest,
    current_user: User = Depends(get_current_user),
    file_service: FileService = Depends(get_file_service),
    _rate_limit: dict = Depends(upload_rate_limit)
):
    """
    Process pasted image from editor.
    
    Args:
        request: FastAPI request object
        image_request: Image paste request data
        current_user: Current authenticated user
        file_service: File service
        _rate_limit: Rate limit check
        
    Returns:
        FileUploadResponse: Upload result
        
    Raises:
        HTTPException: If processing fails
    """
    try:
        # Get client IP
        client_ip = None
        if request.client:
            client_ip = request.client.host
        elif "x-forwarded-for" in request.headers:
            client_ip = request.headers["x-forwarded-for"].split(",")[0].strip()
        elif "x-real-ip" in request.headers:
            client_ip = request.headers["x-real-ip"]
        
        # Parse document ID if provided
        doc_uuid = None
        if image_request.document_id:
            try:
                doc_uuid = uuid.UUID(image_request.document_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid document ID format"
                )
        
        # Process pasted image
        file_record = await file_service.process_pasted_image(
            image_data=image_request.image_data,
            user=current_user,
            folder_path=image_request.folder_path,
            document_id=doc_uuid,
            ip_address=client_ip
        )
        
        logger.info(f"Pasted image processed successfully by {current_user.username}")
        
        return FileUploadResponse(
            id=str(file_record.id),
            filename=file_record.filename,
            original_filename=file_record.original_filename,
            file_size=file_record.file_size,
            mime_type=file_record.mime_type,
            checksum=file_record.checksum,
            created_at=file_record.created_at.isoformat(),
            message="Image processed successfully"
        )
        
    except FileUploadError as e:
        logger.warning(f"Image processing error for {current_user.username}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error during image processing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Image processing failed"
        )


@router.post("/{file_id}/thumbnail", response_model=FileUploadResponse)
async def create_thumbnail(
    file_id: str,
    width: int = 300,
    height: int = 300,
    current_user: User = Depends(get_current_user),
    file_service: FileService = Depends(get_file_service)
):
    """
    Create thumbnail for an image file.
    
    Args:
        file_id: File ID
        width: Thumbnail width
        height: Thumbnail height
        current_user: Current authenticated user
        file_service: File service
        
    Returns:
        FileUploadResponse: Thumbnail creation result
        
    Raises:
        HTTPException: If creation fails
    """
    try:
        file_uuid = uuid.UUID(file_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file ID format"
        )
    
    try:
        # Validate thumbnail size
        if width <= 0 or height <= 0 or width > 1024 or height > 1024:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid thumbnail size (must be between 1 and 1024 pixels)"
            )
        
        thumbnail_record = await file_service.create_thumbnail(
            file_id=file_uuid,
            user=current_user,
            size=(width, height)
        )
        
        if not thumbnail_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found or not an image"
            )
        
        return FileUploadResponse(
            id=str(thumbnail_record.id),
            filename=thumbnail_record.filename,
            original_filename=thumbnail_record.original_filename,
            file_size=thumbnail_record.file_size,
            mime_type=thumbnail_record.mime_type,
            checksum=thumbnail_record.checksum,
            created_at=thumbnail_record.created_at.isoformat(),
            message="Thumbnail created successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating thumbnail: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create thumbnail"
        )


@router.get("/{file_id}/access-logs")
async def get_file_access_logs(
    file_id: str,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    file_service: FileService = Depends(get_file_service)
):
    """
    Get access logs for a file.
    
    Args:
        file_id: File ID
        limit: Maximum number of logs to return
        current_user: Current authenticated user
        file_service: File service
        
    Returns:
        List: Access log entries
        
    Raises:
        HTTPException: If file not found or access denied
    """
    try:
        file_uuid = uuid.UUID(file_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file ID format"
        )
    
    try:
        # Validate limit
        if limit <= 0 or limit > 1000:
            limit = 100
        
        access_logs = await file_service.get_file_access_logs(
            file_id=file_uuid,
            user=current_user,
            limit=limit
        )
        
        return {
            "file_id": file_id,
            "access_logs": access_logs,
            "total_logs": len(access_logs)
        }
        
    except Exception as e:
        logger.error(f"Error getting file access logs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get access logs"
        )


@router.post("/cleanup-orphaned")
async def cleanup_orphaned_files(
    current_user: User = Depends(get_current_user),
    file_service: FileService = Depends(get_file_service)
):
    """
    Clean up orphaned files (admin only).
    
    Args:
        current_user: Current authenticated user
        file_service: File service
        
    Returns:
        MessageResponse: Cleanup result
        
    Raises:
        HTTPException: If not admin or cleanup fails
    """
    try:
        # Check admin permission
        if current_user.role.value != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        cleaned_count = await file_service.cleanup_orphaned_files()
        
        return MessageResponse(
            message=f"Cleaned up {cleaned_count} orphaned files"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during file cleanup: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cleanup orphaned files"
        )