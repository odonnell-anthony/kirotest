"""
Permission service for group-based authorization with path pattern matching.
"""
import logging
import re
import uuid
from typing import List, Optional, Dict, Any, Set
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload
from aioredis import Redis

from app.core.redis import get_redis
from app.models.user import User, UserRole
from app.models.permission import (
    PermissionGroup, Permission, UserGroup, 
    PermissionAction, PermissionEffect
)
from app.services.audit import AuditService

logger = logging.getLogger(__name__)


class PermissionError(Exception):
    """Permission-related errors."""
    pass


class PermissionService:
    """Service for handling group-based permissions with path pattern matching."""
    
    def __init__(self, db: AsyncSession, audit_service: Optional[AuditService] = None):
        self.db = db
        self.audit_service = audit_service or AuditService(db)
        self._cache_ttl = 300  # 5 minutes cache TTL
    
    async def check_permission(
        self, 
        user: User, 
        resource_path: str, 
        action: PermissionAction,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Check if user has permission to perform action on resource.
        
        Args:
            user: User object
            resource_path: Resource path (e.g., '/docs/private/file.md')
            action: Permission action to check
            ip_address: Client IP address for audit logging
            
        Returns:
            bool: True if permission is granted
        """
        try:
            # Admin users have all permissions by default
            if user.role == UserRole.ADMIN:
                await self.audit_service.log_permission_event(
                    action=action.value,
                    user_id=user.id,
                    resource_path=resource_path,
                    permission_action=action.value,
                    granted=True,
                    ip_address=ip_address
                )
                return True
            
            # Check cached permissions first
            cache_key = f"permission:{user.id}:{resource_path}:{action.value}"
            cached_result = await self._get_cached_permission(cache_key)
            if cached_result is not None:
                await self.audit_service.log_permission_event(
                    action=action.value,
                    user_id=user.id,
                    resource_path=resource_path,
                    permission_action=action.value,
                    granted=cached_result,
                    ip_address=ip_address
                )
                return cached_result
            
            # Get user's permission groups and evaluate permissions
            permissions = await self.get_user_permissions(user.id)
            result = await self._evaluate_permissions(permissions, resource_path, action)
            
            # If no explicit permissions found, check default permissions for normal users
            if result is None:
                result = self._check_default_permissions(user.role, action)
            
            # Cache the result
            await self._cache_permission(cache_key, result)
            
            # Log the permission check
            await self.audit_service.log_permission_event(
                action=action.value,
                user_id=user.id,
                resource_path=resource_path,
                permission_action=action.value,
                granted=result,
                ip_address=ip_address
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error checking permission for user {user.id}: {e}")
            # Deny by default on errors
            return False
    
    async def get_user_permissions(self, user_id: uuid.UUID) -> List[Permission]:
        """
        Get all permissions for a user through their groups.
        
        Args:
            user_id: User ID
            
        Returns:
            List[Permission]: List of permissions
        """
        try:
            # Query user groups with permissions
            stmt = (
                select(Permission)
                .join(PermissionGroup)
                .join(UserGroup)
                .where(UserGroup.user_id == user_id)
                .options(selectinload(Permission.group))
                .order_by(Permission.resource_pattern.desc())  # More specific patterns first
            )
            
            result = await self.db.execute(stmt)
            return list(result.scalars().all())
            
        except Exception as e:
            logger.error(f"Error getting user permissions for user {user_id}: {e}")
            return []
    
    async def get_user_groups(self, user_id: uuid.UUID) -> List[PermissionGroup]:
        """
        Get all permission groups for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            List[PermissionGroup]: List of permission groups
        """
        try:
            stmt = (
                select(PermissionGroup)
                .join(UserGroup)
                .where(UserGroup.user_id == user_id)
                .options(selectinload(PermissionGroup.permissions))
            )
            
            result = await self.db.execute(stmt)
            return list(result.scalars().all())
            
        except Exception as e:
            logger.error(f"Error getting user groups for user {user_id}: {e}")
            return []
    
    async def create_permission_group(
        self, 
        name: str, 
        description: Optional[str] = None
    ) -> PermissionGroup:
        """
        Create a new permission group.
        
        Args:
            name: Group name
            description: Group description
            
        Returns:
            PermissionGroup: Created permission group
            
        Raises:
            PermissionError: If group already exists
        """
        try:
            # Check if group already exists
            stmt = select(PermissionGroup).where(PermissionGroup.name == name)
            result = await self.db.execute(stmt)
            existing_group = result.scalar_one_or_none()
            
            if existing_group:
                raise PermissionError(f"Permission group '{name}' already exists")
            
            # Create new group
            group = PermissionGroup(
                name=name,
                description=description
            )
            
            self.db.add(group)
            await self.db.flush()
            
            logger.info(f"Created permission group: {name}")
            return group
            
        except PermissionError:
            raise
        except Exception as e:
            logger.error(f"Error creating permission group '{name}': {e}")
            await self.db.rollback()
            raise PermissionError(f"Failed to create permission group: {e}")
    
    async def create_permission(
        self,
        group_id: uuid.UUID,
        resource_pattern: str,
        action: PermissionAction,
        effect: PermissionEffect
    ) -> Permission:
        """
        Create a new permission rule.
        
        Args:
            group_id: Permission group ID
            resource_pattern: Resource path pattern (e.g., '/docs/private/*')
            action: Permission action
            effect: Permission effect (allow/deny)
            
        Returns:
            Permission: Created permission
            
        Raises:
            PermissionError: If group doesn't exist or pattern is invalid
        """
        try:
            # Validate group exists
            stmt = select(PermissionGroup).where(PermissionGroup.id == group_id)
            result = await self.db.execute(stmt)
            group = result.scalar_one_or_none()
            
            if not group:
                raise PermissionError(f"Permission group {group_id} not found")
            
            # Validate resource pattern
            if not self._validate_resource_pattern(resource_pattern):
                raise PermissionError(f"Invalid resource pattern: {resource_pattern}")
            
            # Create permission
            permission = Permission(
                group_id=group_id,
                resource_pattern=resource_pattern,
                action=action,
                effect=effect
            )
            
            self.db.add(permission)
            await self.db.flush()
            
            # Clear permission cache for affected users
            await self._clear_group_permission_cache(group_id)
            
            logger.info(f"Created permission: {resource_pattern} -> {action.value} ({effect.value})")
            return permission
            
        except PermissionError:
            raise
        except Exception as e:
            logger.error(f"Error creating permission: {e}")
            await self.db.rollback()
            raise PermissionError(f"Failed to create permission: {e}")
    
    async def assign_user_to_group(self, user_id: uuid.UUID, group_id: uuid.UUID) -> UserGroup:
        """
        Assign user to permission group.
        
        Args:
            user_id: User ID
            group_id: Permission group ID
            
        Returns:
            UserGroup: Created user-group association
            
        Raises:
            PermissionError: If user or group doesn't exist, or assignment already exists
        """
        try:
            # Check if assignment already exists
            stmt = select(UserGroup).where(
                and_(UserGroup.user_id == user_id, UserGroup.group_id == group_id)
            )
            result = await self.db.execute(stmt)
            existing_assignment = result.scalar_one_or_none()
            
            if existing_assignment:
                raise PermissionError("User is already assigned to this group")
            
            # Validate user exists
            user_stmt = select(User).where(User.id == user_id)
            user_result = await self.db.execute(user_stmt)
            user = user_result.scalar_one_or_none()
            
            if not user:
                raise PermissionError(f"User {user_id} not found")
            
            # Validate group exists
            group_stmt = select(PermissionGroup).where(PermissionGroup.id == group_id)
            group_result = await self.db.execute(group_stmt)
            group = group_result.scalar_one_or_none()
            
            if not group:
                raise PermissionError(f"Permission group {group_id} not found")
            
            # Create assignment
            user_group = UserGroup(
                user_id=user_id,
                group_id=group_id
            )
            
            self.db.add(user_group)
            await self.db.flush()
            
            # Clear user's permission cache
            await self._clear_user_permission_cache(user_id)
            
            logger.info(f"Assigned user {user.username} to group {group.name}")
            return user_group
            
        except PermissionError:
            raise
        except Exception as e:
            logger.error(f"Error assigning user to group: {e}")
            await self.db.rollback()
            raise PermissionError(f"Failed to assign user to group: {e}")
    
    async def remove_user_from_group(self, user_id: uuid.UUID, group_id: uuid.UUID) -> bool:
        """
        Remove user from permission group.
        
        Args:
            user_id: User ID
            group_id: Permission group ID
            
        Returns:
            bool: True if removed successfully
        """
        try:
            stmt = select(UserGroup).where(
                and_(UserGroup.user_id == user_id, UserGroup.group_id == group_id)
            )
            result = await self.db.execute(stmt)
            user_group = result.scalar_one_or_none()
            
            if not user_group:
                return False
            
            await self.db.delete(user_group)
            await self.db.flush()
            
            # Clear user's permission cache
            await self._clear_user_permission_cache(user_id)
            
            logger.info(f"Removed user {user_id} from group {group_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error removing user from group: {e}")
            await self.db.rollback()
            return False
    
    async def evaluate_path_patterns(
        self, 
        user: User, 
        path: str
    ) -> List[Permission]:
        """
        Get all permissions that match a specific path for a user.
        
        Args:
            user: User object
            path: Resource path to evaluate
            
        Returns:
            List[Permission]: Matching permissions
        """
        try:
            permissions = await self.get_user_permissions(user.id)
            matching_permissions = []
            
            for permission in permissions:
                if self._match_pattern(permission.resource_pattern, path):
                    matching_permissions.append(permission)
            
            return matching_permissions
            
        except Exception as e:
            logger.error(f"Error evaluating path patterns for user {user.id}: {e}")
            return []
    
    def _validate_resource_pattern(self, pattern: str) -> bool:
        """
        Validate resource pattern format.
        
        Args:
            pattern: Resource pattern to validate
            
        Returns:
            bool: True if pattern is valid
        """
        try:
            # Basic validation - should start with / and contain valid characters
            if not pattern.startswith('/'):
                return False
            
            # Check for valid characters (alphanumeric, /, -, _, *, ?)
            if not re.match(r'^[/a-zA-Z0-9_\-*?]+$', pattern):
                return False
            
            return True
            
        except Exception:
            return False
    
    def _match_pattern(self, pattern: str, path: str) -> bool:
        """
        Check if path matches pattern using glob-style matching.
        
        Args:
            pattern: Pattern to match against (e.g., '/docs/private/*')
            path: Path to check (e.g., '/docs/private/file.md')
            
        Returns:
            bool: True if path matches pattern
        """
        try:
            # Convert glob pattern to regex
            regex_pattern = pattern.replace('*', '.*').replace('?', '.')
            regex_pattern = f'^{regex_pattern}$'
            
            return bool(re.match(regex_pattern, path))
            
        except Exception:
            return False
    
    async def _evaluate_permissions(
        self, 
        permissions: List[Permission], 
        resource_path: str, 
        action: PermissionAction
    ) -> Optional[bool]:
        """
        Evaluate permissions using deny-by-default policy.
        
        Args:
            permissions: List of permissions to evaluate
            resource_path: Resource path
            action: Permission action
            
        Returns:
            Optional[bool]: True if allowed, False if denied, None if no matching permissions
        """
        matching_permissions = []
        
        # Find all matching permissions
        for permission in permissions:
            if (permission.action == action and 
                self._match_pattern(permission.resource_pattern, resource_path)):
                matching_permissions.append(permission)
        
        if not matching_permissions:
            return None  # No matching permissions found
        
        # Sort by specificity (longer patterns are more specific)
        matching_permissions.sort(
            key=lambda p: len(p.resource_pattern.replace('*', '')), 
            reverse=True
        )
        
        # Apply deny-by-default: explicit deny takes precedence
        for permission in matching_permissions:
            if permission.effect == PermissionEffect.DENY:
                return False
        
        # If no deny found, check for allow
        for permission in matching_permissions:
            if permission.effect == PermissionEffect.ALLOW:
                return True
        
        return False  # Deny by default
    
    def _check_default_permissions(self, role: UserRole, action: PermissionAction) -> bool:
        """
        Check default permissions for user roles.
        
        Args:
            role: User role
            action: Permission action
            
        Returns:
            bool: True if action is allowed by default
        """
        if role == UserRole.ADMIN:
            return True
        
        if role == UserRole.NORMAL:
            # Normal users have basic read and edit permissions by default
            return action in [PermissionAction.READ_PAGES, PermissionAction.EDIT_PAGES]
        
        return False
    
    async def _get_cached_permission(self, cache_key: str) -> Optional[bool]:
        """Get cached permission result."""
        try:
            redis = await get_redis()
            cached_value = await redis.get(cache_key)
            
            if cached_value is not None:
                return cached_value.lower() == 'true'
            
            return None
            
        except Exception as e:
            logger.warning(f"Error getting cached permission: {e}")
            return None
    
    async def _cache_permission(self, cache_key: str, result: bool) -> None:
        """Cache permission result."""
        try:
            redis = await get_redis()
            await redis.setex(cache_key, self._cache_ttl, str(result).lower())
            
        except Exception as e:
            logger.warning(f"Error caching permission: {e}")
    
    async def _clear_user_permission_cache(self, user_id: uuid.UUID) -> None:
        """Clear all cached permissions for a user."""
        try:
            redis = await get_redis()
            pattern = f"permission:{user_id}:*"
            
            keys = []
            async for key in redis.scan_iter(match=pattern):
                keys.append(key)
            
            if keys:
                await redis.delete(*keys)
                logger.info(f"Cleared {len(keys)} cached permissions for user {user_id}")
                
        except Exception as e:
            logger.warning(f"Error clearing user permission cache: {e}")
    
    async def _clear_group_permission_cache(self, group_id: uuid.UUID) -> None:
        """Clear cached permissions for all users in a group."""
        try:
            # Get all users in the group
            stmt = select(UserGroup.user_id).where(UserGroup.group_id == group_id)
            result = await self.db.execute(stmt)
            user_ids = [row[0] for row in result.fetchall()]
            
            # Clear cache for each user
            for user_id in user_ids:
                await self._clear_user_permission_cache(user_id)
                
        except Exception as e:
            logger.warning(f"Error clearing group permission cache: {e}")
    
    async def get_effective_permissions(
        self, 
        user: User, 
        resource_path: str
    ) -> Dict[str, bool]:
        """
        Get effective permissions for all actions on a resource.
        
        Args:
            user: User object
            resource_path: Resource path
            
        Returns:
            Dict[str, bool]: Dictionary of action -> allowed mapping
        """
        effective_permissions = {}
        
        for action in PermissionAction:
            effective_permissions[action.value] = await self.check_permission(
                user, resource_path, action
            )
        
        return effective_permissions