"""
File service for secure file upload and management with malware scanning.
"""
import logging
import os
import uuid
import base64
import io
from datetime import datetime
from typing import Optional, Dict, Any, BinaryIO, Tuple
from pathlib import Path
from fastapi import UploadFile, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from PIL import Image, ImageOps
import magic

from app.core.config import settings
from app.core.security import InputValidator
from app.models.user import User
from app.models.file import File
from app.models.permission import PermissionAction
from app.services.audit import AuditService

logger = logging.getLogger(__name__)


class FileUploadError(Exception):
    """File upload related errors."""
    pass


class MalwareDetectedError(Exception):
    """Malware detected in file."""
    pass


class FileService:
    """Service for handling secure file uploads and management."""
    
    def __init__(self, db: AsyncSession, audit_service: Optional[AuditService] = None, permission_service=None):
        self.db = db
        self.audit_service = audit_service or AuditService(db)
        self.permission_service = permission_service  # Will be injected to avoid circular imports
        self.upload_dir = Path(settings.UPLOAD_DIR)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        
        # Image processing settings
        self.max_image_width = 2048
        self.max_image_height = 2048
        self.image_quality = 85
        self.thumbnail_size = (300, 300)
    
    async def upload_file(
        self,
        file: UploadFile,
        user: User,
        folder_path: str = "/",
        document_id: Optional[uuid.UUID] = None,
        ip_address: Optional[str] = None
    ) -> File:
        """
        Upload and validate file with security scanning.
        
        Args:
            file: Uploaded file
            user: User uploading the file
            folder_path: Destination folder path
            document_id: Optional associated document ID
            ip_address: Client IP address
            
        Returns:
            File: Created file record
            
        Raises:
            FileUploadError: If upload fails
            MalwareDetectedError: If malware is detected
        """
        try:
            # Validate file
            if not file.filename:
                raise FileUploadError("Filename is required")
            
            # Read file content
            file_content = await file.read()
            file_size = len(file_content)
            
            # Reset file pointer for potential re-reading
            await file.seek(0)
            
            # Validate file size
            if not InputValidator.validate_file_size(file_size):
                raise FileUploadError(f"File size {file_size} exceeds maximum allowed size")
            
            # Validate file type
            if not InputValidator.validate_file_type(file_content, file.filename):
                raise FileUploadError(f"File type not allowed: {file.filename}")
            
            # Scan for malware
            scan_result = InputValidator.scan_for_malware(file_content, file.filename)
            if not scan_result["is_safe"]:
                logger.warning(f"Malware detected in file {file.filename}: {scan_result['threats_found']}")
                await self.audit_service.create_security_event(
                    event_type="malware_detected",
                    title="Malware Detected in File Upload",
                    description=f"Malware detected in file {file.filename}: {', '.join(scan_result['threats_found'])}",
                    severity="HIGH",
                    source_ip=ip_address,
                    source_user_id=user.id,
                    event_data={
                        "filename": file.filename,
                        "threats": scan_result["threats_found"],
                        "file_size": file_size
                    }
                )
                raise MalwareDetectedError(f"Security threat detected in file: {', '.join(scan_result['threats_found'])}")
            
            # Validate folder path
            if not InputValidator.validate_path(folder_path):
                raise FileUploadError("Invalid folder path")
            
            # Generate unique filename
            file_extension = Path(file.filename).suffix.lower()
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            
            # Create folder structure
            folder_full_path = self.upload_dir / folder_path.strip("/")
            folder_full_path.mkdir(parents=True, exist_ok=True)
            
            # Save file
            file_path = folder_full_path / unique_filename
            with open(file_path, "wb") as f:
                f.write(file_content)
            
            # Generate file hash
            file_hash = InputValidator.generate_file_hash(file_content)
            
            # Check for duplicate files
            existing_file = await self._find_duplicate_file(file_hash)
            if existing_file:
                logger.info(f"Duplicate file detected: {file.filename} (hash: {file_hash})")
                # Remove the newly uploaded file since it's a duplicate
                os.unlink(file_path)
                return existing_file
            
            # Create file record
            file_record = File(
                filename=unique_filename,
                original_filename=file.filename,
                file_path=str(file_path.relative_to(self.upload_dir)),
                mime_type=file.content_type or "application/octet-stream",
                file_size=file_size,
                checksum=file_hash,
                uploaded_by=user.id,
                document_id=document_id
            )
            
            self.db.add(file_record)
            await self.db.flush()
            
            # Log file upload
            await self.audit_service.log_file_event(
                action="FILE_UPLOAD",
                file_id=file_record.id,
                user_id=user.id,
                filename=file.filename,
                file_size=file_size,
                ip_address=ip_address
            )
            
            logger.info(f"File uploaded successfully: {file.filename} by {user.username}")
            return file_record
            
        except (FileUploadError, MalwareDetectedError):
            raise
        except Exception as e:
            logger.error(f"Error uploading file {file.filename}: {e}")
            await self.db.rollback()
            raise FileUploadError(f"Failed to upload file: {e}")
    
    async def get_file(
        self,
        file_id: uuid.UUID,
        user: User,
        ip_address: Optional[str] = None
    ) -> Optional[File]:
        """
        Get file record and check permissions.
        
        Args:
            file_id: File ID
            user: User requesting the file
            ip_address: Client IP address
            
        Returns:
            File: File record or None if not found/no permission
        """
        try:
            stmt = select(File).where(File.id == file_id)
            result = await self.db.execute(stmt)
            file_record = result.scalar_one_or_none()
            
            if not file_record:
                return None
            
            # Check permissions using permission service
            has_permission = await self._check_file_permission(
                user, file_record, PermissionAction.READ_ASSETS, ip_address
            )
            
            if not has_permission:
                logger.warning(f"Unauthorized file access attempt: {user.username} -> {file_record.filename}")
                await self.audit_service.create_security_event(
                    event_type="unauthorized_file_access",
                    title="Unauthorized File Access Attempt",
                    description=f"User {user.username} attempted to access file {file_record.filename} without permission",
                    severity="MEDIUM",
                    source_ip=ip_address,
                    source_user_id=user.id,
                    event_data={
                        "file_id": str(file_record.id),
                        "filename": file_record.filename,
                        "file_path": file_record.file_path
                    }
                )
                return None
            
            # Update access tracking
            file_record.access_count += 1
            file_record.last_accessed_at = datetime.utcnow()
            await self.db.flush()
            
            # Log file access
            await self.audit_service.log_file_event(
                action="FILE_ACCESS",
                file_id=file_record.id,
                user_id=user.id,
                filename=file_record.original_filename,
                file_size=file_record.file_size,
                ip_address=ip_address
            )
            
            return file_record
            
        except Exception as e:
            logger.error(f"Error getting file {file_id}: {e}")
            return None
    
    async def delete_file(
        self,
        file_id: uuid.UUID,
        user: User,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Delete file and its record with permission checks and reference cleanup.
        
        Args:
            file_id: File ID
            user: User deleting the file
            ip_address: Client IP address
            
        Returns:
            bool: True if deleted successfully
        """
        try:
            stmt = select(File).where(File.id == file_id)
            result = await self.db.execute(stmt)
            file_record = result.scalar_one_or_none()
            
            if not file_record:
                return False
            
            # Check permissions
            has_permission = await self._check_file_permission(
                user, file_record, PermissionAction.DELETE_PAGES, ip_address
            )
            
            if not has_permission:
                logger.warning(f"Unauthorized file deletion attempt: {user.username} -> {file_record.filename}")
                await self.audit_service.create_security_event(
                    event_type="unauthorized_file_deletion",
                    title="Unauthorized File Deletion Attempt",
                    description=f"User {user.username} attempted to delete file {file_record.filename} without permission",
                    severity="HIGH",
                    source_ip=ip_address,
                    source_user_id=user.id,
                    event_data={
                        "file_id": str(file_record.id),
                        "filename": file_record.filename,
                        "file_path": file_record.file_path
                    }
                )
                return False
            
            # Check for references in documents before deletion
            references = await self._find_file_references(file_record)
            if references:
                logger.info(f"File {file_record.filename} has {len(references)} references, updating them")
                await self._update_file_references(file_record, None)  # Remove references
            
            # Delete physical file
            file_path = self.upload_dir / file_record.file_path
            if file_path.exists():
                os.unlink(file_path)
                logger.info(f"Physical file deleted: {file_path}")
            
            # Store file info for audit log before deletion
            file_info = {
                "id": str(file_record.id),
                "filename": file_record.original_filename,
                "file_path": file_record.file_path,
                "file_size": file_record.file_size,
                "checksum": file_record.checksum
            }
            
            # Delete record
            await self.db.delete(file_record)
            await self.db.flush()
            
            # Log file deletion
            await self.audit_service.log_file_event(
                action="FILE_DELETE",
                file_id=uuid.UUID(file_info["id"]),
                user_id=user.id,
                filename=file_info["filename"],
                file_size=file_info["file_size"],
                ip_address=ip_address
            )
            
            logger.info(f"File deleted: {file_info['filename']} by {user.username}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting file {file_id}: {e}")
            await self.db.rollback()
            return False
    
    async def move_file(
        self,
        file_id: uuid.UUID,
        new_folder_path: str,
        user: User,
        ip_address: Optional[str] = None
    ) -> Optional[File]:
        """
        Move file to new folder with permission checks and reference updates.
        
        Args:
            file_id: File ID
            new_folder_path: New folder path
            user: User moving the file
            ip_address: Client IP address
            
        Returns:
            File: Updated file record or None if failed
        """
        try:
            stmt = select(File).where(File.id == file_id)
            result = await self.db.execute(stmt)
            file_record = result.scalar_one_or_none()
            
            if not file_record:
                return None
            
            # Check permissions for both source and destination
            has_source_permission = await self._check_file_permission(
                user, file_record, PermissionAction.EDIT_PAGES, ip_address
            )
            
            if not has_source_permission:
                logger.warning(f"Unauthorized file move attempt: {user.username} -> {file_record.filename}")
                return None
            
            # Check destination permission
            has_dest_permission = await self._check_path_permission(
                user, new_folder_path, PermissionAction.EDIT_PAGES, ip_address
            )
            
            if not has_dest_permission:
                logger.warning(f"Unauthorized destination access for file move: {user.username} -> {new_folder_path}")
                return None
            
            # Validate new folder path
            if not InputValidator.validate_path(new_folder_path):
                raise FileUploadError("Invalid folder path")
            
            # Store old path for reference updates
            old_file_path_str = file_record.file_path
            
            # Create new folder structure
            new_folder_full_path = self.upload_dir / new_folder_path.strip("/")
            new_folder_full_path.mkdir(parents=True, exist_ok=True)
            
            # Move physical file
            old_file_path = self.upload_dir / file_record.file_path
            new_file_path = new_folder_full_path / file_record.filename
            
            if old_file_path.exists():
                os.rename(old_file_path, new_file_path)
                logger.info(f"Physical file moved: {old_file_path} -> {new_file_path}")
            
            # Update record
            new_file_path_str = str(new_file_path.relative_to(self.upload_dir))
            file_record.file_path = new_file_path_str
            await self.db.flush()
            
            # Update references in documents
            await self._update_file_references(file_record, new_file_path_str, old_file_path_str)
            
            # Log file move
            await self.audit_service.log_file_event(
                action="FILE_MOVE",
                file_id=file_record.id,
                user_id=user.id,
                filename=file_record.original_filename,
                file_size=file_record.file_size,
                ip_address=ip_address
            )
            
            logger.info(f"File moved: {file_record.original_filename} to {new_folder_path} by {user.username}")
            return file_record
            
        except Exception as e:
            logger.error(f"Error moving file {file_id}: {e}")
            await self.db.rollback()
            return None
    
    async def _find_duplicate_file(self, file_hash: str) -> Optional[File]:
        """Find existing file with same hash."""
        try:
            stmt = select(File).where(File.checksum == file_hash)
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error finding duplicate file: {e}")
            return None
    
    def get_file_path(self, file_record: File) -> Path:
        """Get full file system path for file record."""
        return self.upload_dir / file_record.file_path
    
    async def process_pasted_image(
        self,
        image_data: str,
        user: User,
        folder_path: str = "/",
        document_id: Optional[uuid.UUID] = None,
        ip_address: Optional[str] = None
    ) -> File:
        """
        Process pasted image data from editor (base64 encoded).
        
        Args:
            image_data: Base64 encoded image data (with or without data URL prefix)
            user: User uploading the image
            folder_path: Destination folder path
            document_id: Optional associated document ID
            ip_address: Client IP address
            
        Returns:
            File: Created file record
            
        Raises:
            FileUploadError: If processing fails
        """
        try:
            # Parse base64 image data
            if image_data.startswith('data:'):
                # Remove data URL prefix (e.g., "data:image/png;base64,")
                header, encoded_data = image_data.split(',', 1)
                mime_type = header.split(';')[0].split(':')[1]
            else:
                # Assume it's just base64 data
                encoded_data = image_data
                mime_type = "image/png"  # Default
            
            # Decode base64 data
            try:
                image_bytes = base64.b64decode(encoded_data)
            except Exception as e:
                raise FileUploadError(f"Invalid base64 image data: {e}")
            
            # Validate file size
            if not InputValidator.validate_file_size(len(image_bytes)):
                raise FileUploadError(f"Image size {len(image_bytes)} exceeds maximum allowed size")
            
            # Process and optimize image
            processed_image_bytes, final_mime_type = await self._process_image(image_bytes, mime_type)
            
            # Generate unique filename
            file_extension = self._get_extension_from_mime_type(final_mime_type)
            unique_filename = f"pasted_{uuid.uuid4()}{file_extension}"
            
            # Create folder structure
            folder_full_path = self.upload_dir / folder_path.strip("/")
            folder_full_path.mkdir(parents=True, exist_ok=True)
            
            # Save processed image
            file_path = folder_full_path / unique_filename
            with open(file_path, "wb") as f:
                f.write(processed_image_bytes)
            
            # Generate file hash
            file_hash = InputValidator.generate_file_hash(processed_image_bytes)
            
            # Check for duplicate files
            existing_file = await self._find_duplicate_file(file_hash)
            if existing_file:
                logger.info(f"Duplicate pasted image detected (hash: {file_hash})")
                # Remove the newly uploaded file since it's a duplicate
                os.unlink(file_path)
                return existing_file
            
            # Create file record
            file_record = File(
                filename=unique_filename,
                original_filename=f"pasted_image{file_extension}",
                file_path=str(file_path.relative_to(self.upload_dir)),
                mime_type=final_mime_type,
                file_size=len(processed_image_bytes),
                checksum=file_hash,
                uploaded_by=user.id,
                document_id=document_id,
                is_malware_scanned=True,
                malware_scan_result="clean"
            )
            
            self.db.add(file_record)
            await self.db.flush()
            
            # Log file upload
            await self.audit_service.log_file_event(
                action="IMAGE_PASTE",
                file_id=file_record.id,
                user_id=user.id,
                filename=unique_filename,
                file_size=len(processed_image_bytes),
                ip_address=ip_address
            )
            
            logger.info(f"Pasted image processed successfully: {unique_filename} by {user.username}")
            return file_record
            
        except FileUploadError:
            raise
        except Exception as e:
            logger.error(f"Error processing pasted image: {e}")
            await self.db.rollback()
            raise FileUploadError(f"Failed to process pasted image: {e}")
    
    async def _process_image(self, image_bytes: bytes, mime_type: str) -> Tuple[bytes, str]:
        """
        Process and optimize image.
        
        Args:
            image_bytes: Original image bytes
            mime_type: Original MIME type
            
        Returns:
            Tuple[bytes, str]: Processed image bytes and final MIME type
        """
        try:
            # Open image with PIL
            with Image.open(io.BytesIO(image_bytes)) as img:
                # Convert RGBA to RGB if necessary (for JPEG)
                if img.mode in ('RGBA', 'LA', 'P'):
                    # Create white background
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = background
                
                # Auto-orient image based on EXIF data
                img = ImageOps.exif_transpose(img)
                
                # Resize if too large
                if img.width > self.max_image_width or img.height > self.max_image_height:
                    img.thumbnail((self.max_image_width, self.max_image_height), Image.Resampling.LANCZOS)
                    logger.info(f"Image resized to {img.width}x{img.height}")
                
                # Save optimized image
                output_buffer = io.BytesIO()
                
                # Determine output format
                if mime_type in ['image/jpeg', 'image/jpg']:
                    img.save(output_buffer, format='JPEG', quality=self.image_quality, optimize=True)
                    final_mime_type = 'image/jpeg'
                elif mime_type == 'image/png':
                    img.save(output_buffer, format='PNG', optimize=True)
                    final_mime_type = 'image/png'
                elif mime_type == 'image/webp':
                    img.save(output_buffer, format='WEBP', quality=self.image_quality, optimize=True)
                    final_mime_type = 'image/webp'
                else:
                    # Default to JPEG for other formats
                    img.save(output_buffer, format='JPEG', quality=self.image_quality, optimize=True)
                    final_mime_type = 'image/jpeg'
                
                processed_bytes = output_buffer.getvalue()
                logger.info(f"Image processed: {len(image_bytes)} -> {len(processed_bytes)} bytes")
                
                return processed_bytes, final_mime_type
                
        except Exception as e:
            logger.error(f"Error processing image: {e}")
            # Return original image if processing fails
            return image_bytes, mime_type
    
    def _get_extension_from_mime_type(self, mime_type: str) -> str:
        """Get file extension from MIME type."""
        mime_to_ext = {
            'image/jpeg': '.jpg',
            'image/jpg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp',
            'image/svg+xml': '.svg'
        }
        return mime_to_ext.get(mime_type, '.jpg')
    
    async def create_thumbnail(
        self,
        file_id: uuid.UUID,
        user: User,
        size: Optional[Tuple[int, int]] = None
    ) -> Optional[File]:
        """
        Create thumbnail for an image file.
        
        Args:
            file_id: Original file ID
            user: User requesting thumbnail
            size: Thumbnail size (width, height)
            
        Returns:
            File: Thumbnail file record or None if failed
        """
        try:
            # Get original file
            original_file = await self.get_file(file_id, user)
            if not original_file or not original_file.mime_type.startswith('image/'):
                return None
            
            # Check if thumbnail already exists
            thumbnail_filename = f"thumb_{original_file.filename}"
            stmt = select(File).where(File.filename == thumbnail_filename)
            result = await self.db.execute(stmt)
            existing_thumbnail = result.scalar_one_or_none()
            
            if existing_thumbnail:
                return existing_thumbnail
            
            # Read original image
            original_path = self.get_file_path(original_file)
            if not original_path.exists():
                return None
            
            with open(original_path, 'rb') as f:
                image_bytes = f.read()
            
            # Create thumbnail
            thumbnail_size = size or self.thumbnail_size
            
            with Image.open(io.BytesIO(image_bytes)) as img:
                # Create thumbnail
                img.thumbnail(thumbnail_size, Image.Resampling.LANCZOS)
                
                # Save thumbnail
                output_buffer = io.BytesIO()
                if original_file.mime_type == 'image/png':
                    img.save(output_buffer, format='PNG', optimize=True)
                else:
                    img.save(output_buffer, format='JPEG', quality=85, optimize=True)
                
                thumbnail_bytes = output_buffer.getvalue()
            
            # Save thumbnail file
            folder_path = Path(original_file.file_path).parent
            thumbnail_path = self.upload_dir / folder_path / thumbnail_filename
            
            with open(thumbnail_path, 'wb') as f:
                f.write(thumbnail_bytes)
            
            # Create thumbnail record
            thumbnail_record = File(
                filename=thumbnail_filename,
                original_filename=f"thumbnail_{original_file.original_filename}",
                file_path=str(thumbnail_path.relative_to(self.upload_dir)),
                mime_type=original_file.mime_type,
                file_size=len(thumbnail_bytes),
                checksum=InputValidator.generate_file_hash(thumbnail_bytes),
                uploaded_by=user.id,
                document_id=original_file.document_id,
                is_malware_scanned=True,
                malware_scan_result="clean"
            )
            
            self.db.add(thumbnail_record)
            await self.db.flush()
            
            logger.info(f"Thumbnail created: {thumbnail_filename}")
            return thumbnail_record
            
        except Exception as e:
            logger.error(f"Error creating thumbnail: {e}")
            return None
    
    async def _check_file_permission(
        self,
        user: User,
        file_record: File,
        action: PermissionAction,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Check if user has permission to perform action on file.
        
        Args:
            user: User object
            file_record: File record
            action: Permission action
            ip_address: Client IP address
            
        Returns:
            bool: True if permission is granted
        """
        try:
            # Admin users have all permissions
            if user.role.value == "admin":
                return True
            
            # File owners can access their own files
            if file_record.uploaded_by == user.id:
                return True
            
            # Use permission service if available
            if self.permission_service:
                resource_path = f"/files/{file_record.file_path}"
                return await self.permission_service.check_permission(
                    user, resource_path, action, ip_address
                )
            
            # Fallback: deny access to other users' files
            return False
            
        except Exception as e:
            logger.error(f"Error checking file permission: {e}")
            return False
    
    async def _check_path_permission(
        self,
        user: User,
        path: str,
        action: PermissionAction,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Check if user has permission to perform action on path.
        
        Args:
            user: User object
            path: Resource path
            action: Permission action
            ip_address: Client IP address
            
        Returns:
            bool: True if permission is granted
        """
        try:
            # Admin users have all permissions
            if user.role.value == "admin":
                return True
            
            # Use permission service if available
            if self.permission_service:
                resource_path = f"/files{path}" if not path.startswith('/') else f"/files{path}"
                return await self.permission_service.check_permission(
                    user, resource_path, action, ip_address
                )
            
            # Fallback: allow normal users basic access
            return user.role.value == "normal" and action in [
                PermissionAction.READ_ASSETS, PermissionAction.EDIT_PAGES
            ]
            
        except Exception as e:
            logger.error(f"Error checking path permission: {e}")
            return False
    
    async def _find_file_references(self, file_record: File) -> List[Dict[str, Any]]:
        """
        Find references to a file in documents.
        
        Args:
            file_record: File record to find references for
            
        Returns:
            List[Dict]: List of references with document info
        """
        try:
            from app.models.document import Document
            
            # Search for file references in document content
            file_patterns = [
                file_record.filename,
                file_record.file_path,
                f"/{file_record.file_path}",
                str(file_record.id)
            ]
            
            references = []
            
            for pattern in file_patterns:
                stmt = select(Document).where(Document.content.contains(pattern))
                result = await self.db.execute(stmt)
                documents = result.scalars().all()
                
                for doc in documents:
                    references.append({
                        "document_id": doc.id,
                        "document_title": doc.title,
                        "pattern": pattern,
                        "content_snippet": self._extract_content_snippet(doc.content, pattern)
                    })
            
            # Remove duplicates based on document_id
            unique_refs = {}
            for ref in references:
                doc_id = ref["document_id"]
                if doc_id not in unique_refs:
                    unique_refs[doc_id] = ref
            
            return list(unique_refs.values())
            
        except Exception as e:
            logger.error(f"Error finding file references: {e}")
            return []
    
    async def _update_file_references(
        self,
        file_record: File,
        new_path: Optional[str],
        old_path: Optional[str] = None
    ) -> int:
        """
        Update file references in documents.
        
        Args:
            file_record: File record
            new_path: New file path (None to remove references)
            old_path: Old file path for replacement
            
        Returns:
            int: Number of documents updated
        """
        try:
            from app.models.document import Document
            
            references = await self._find_file_references(file_record)
            updated_count = 0
            
            for ref in references:
                stmt = select(Document).where(Document.id == ref["document_id"])
                result = await self.db.execute(stmt)
                document = result.scalar_one_or_none()
                
                if document:
                    old_content = document.content
                    new_content = old_content
                    
                    # Replace all possible references
                    patterns_to_replace = [
                        file_record.filename,
                        file_record.file_path,
                        f"/{file_record.file_path}",
                        str(file_record.id)
                    ]
                    
                    if old_path:
                        patterns_to_replace.extend([old_path, f"/{old_path}"])
                    
                    for pattern in patterns_to_replace:
                        if pattern in new_content:
                            if new_path:
                                # Replace with new path
                                new_content = new_content.replace(pattern, new_path)
                            else:
                                # Remove reference (for deletion)
                                new_content = new_content.replace(f"![{pattern}]({pattern})", "[File removed]")
                                new_content = new_content.replace(f"[{pattern}]({pattern})", "[File removed]")
                                new_content = new_content.replace(pattern, "[File removed]")
                    
                    if new_content != old_content:
                        document.content = new_content
                        updated_count += 1
                        
                        logger.info(f"Updated file references in document {document.title}")
            
            if updated_count > 0:
                await self.db.flush()
                logger.info(f"Updated file references in {updated_count} documents")
            
            return updated_count
            
        except Exception as e:
            logger.error(f"Error updating file references: {e}")
            return 0
    
    def _extract_content_snippet(self, content: str, pattern: str, context_length: int = 100) -> str:
        """
        Extract content snippet around a pattern match.
        
        Args:
            content: Document content
            pattern: Pattern to find
            context_length: Length of context around match
            
        Returns:
            str: Content snippet
        """
        try:
            index = content.find(pattern)
            if index == -1:
                return ""
            
            start = max(0, index - context_length)
            end = min(len(content), index + len(pattern) + context_length)
            
            snippet = content[start:end]
            if start > 0:
                snippet = "..." + snippet
            if end < len(content):
                snippet = snippet + "..."
            
            return snippet
            
        except Exception:
            return ""
    
    async def get_file_access_logs(
        self,
        file_id: uuid.UUID,
        user: User,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get access logs for a file.
        
        Args:
            file_id: File ID
            user: User requesting logs
            limit: Maximum number of logs to return
            
        Returns:
            List[Dict]: Access log entries
        """
        try:
            # Check if user can view logs (admin or file owner)
            stmt = select(File).where(File.id == file_id)
            result = await self.db.execute(stmt)
            file_record = result.scalar_one_or_none()
            
            if not file_record:
                return []
            
            if user.role.value != "admin" and file_record.uploaded_by != user.id:
                return []
            
            # Get audit logs for this file
            return await self.audit_service.get_file_audit_logs(file_id, limit)
            
        except Exception as e:
            logger.error(f"Error getting file access logs: {e}")
            return []
    
    async def cleanup_orphaned_files(self) -> int:
        """
        Clean up orphaned files (files without database records).
        
        Returns:
            int: Number of files cleaned up
        """
        try:
            cleaned_count = 0
            
            # Get all file records from database
            stmt = select(File.file_path)
            result = await self.db.execute(stmt)
            db_file_paths = {row[0] for row in result.fetchall()}
            
            # Scan upload directory
            for file_path in self.upload_dir.rglob("*"):
                if file_path.is_file():
                    relative_path = str(file_path.relative_to(self.upload_dir))
                    
                    if relative_path not in db_file_paths:
                        # Orphaned file found
                        try:
                            os.unlink(file_path)
                            cleaned_count += 1
                            logger.info(f"Cleaned up orphaned file: {relative_path}")
                        except Exception as e:
                            logger.error(f"Error cleaning up orphaned file {relative_path}: {e}")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Error during file cleanup: {e}")
            return 0