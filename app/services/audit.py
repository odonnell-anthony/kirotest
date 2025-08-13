"""
Audit service for security and compliance tracking.
"""
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.audit import AuditLog, SecurityEvent, AuditAction, AuditSeverity
from app.models.user import User


class AuditService:
    """Service for managing audit logs and security events."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def log_action(
        self,
        action: AuditAction,
        description: str,
        user_id: Optional[uuid.UUID] = None,
        session_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        resource_path: Optional[str] = None,
        request_method: Optional[str] = None,
        request_path: Optional[str] = None,
        request_params: Optional[Dict[str, Any]] = None,
        response_status: Optional[int] = None,
        response_time_ms: Optional[int] = None,
        severity: AuditSeverity = AuditSeverity.LOW,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AuditLog:
        """Log an audit action."""
        
        audit_log = AuditLog(
            action=action,
            severity=severity,
            description=description,
            user_id=user_id,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            resource_path=resource_path,
            request_method=request_method,
            request_path=request_path,
            request_params=request_params or {},
            response_status=response_status,
            response_time_ms=response_time_ms,
            metadata=metadata or {}
        )
        
        self.db.add(audit_log)
        await self.db.flush()
        return audit_log
    
    async def log_authentication_event(
        self,
        action: AuditAction,
        user_id: Optional[uuid.UUID],
        ip_address: str,
        user_agent: str,
        success: bool,
        details: Optional[str] = None
    ) -> AuditLog:
        """Log authentication-related events."""
        
        severity = AuditSeverity.LOW if success else AuditSeverity.MEDIUM
        description = f"Authentication {action.value}"
        if details:
            description += f": {details}"
        
        return await self.log_action(
            action=action,
            description=description,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            severity=severity,
            metadata={"success": success}
        )
    
    async def log_authentication_success(
        self,
        user_id: uuid.UUID,
        username: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> AuditLog:
        """Log successful authentication."""
        
        return await self.log_action(
            action=AuditAction.LOGIN,
            description=f"User login successful: {username}",
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            severity=AuditSeverity.LOW,
            metadata={"success": True, "username": username}
        )
    
    async def log_authentication_failure(
        self,
        username: str,
        reason: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> AuditLog:
        """Log failed authentication attempt."""
        
        return await self.log_action(
            action=AuditAction.LOGIN,
            description=f"User login failed: {username} - {reason}",
            ip_address=ip_address,
            user_agent=user_agent,
            severity=AuditSeverity.MEDIUM,
            metadata={"success": False, "username": username, "reason": reason}
        )
    
    async def log_document_event(
        self,
        action: AuditAction,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
        document_title: str,
        ip_address: Optional[str] = None,
        changes: Optional[Dict[str, Any]] = None
    ) -> AuditLog:
        """Log document-related events."""
        
        description = f"Document {action.value}: {document_title}"
        
        return await self.log_action(
            action=action,
            description=description,
            user_id=user_id,
            ip_address=ip_address,
            resource_type="document",
            resource_id=str(document_id),
            severity=AuditSeverity.LOW,
            metadata={"changes": changes or {}}
        )
    
    async def log_file_event(
        self,
        action: AuditAction,
        file_id: uuid.UUID,
        user_id: uuid.UUID,
        filename: str,
        file_size: int,
        ip_address: Optional[str] = None
    ) -> AuditLog:
        """Log file-related events."""
        
        description = f"File {action.value}: {filename} ({file_size} bytes)"
        
        return await self.log_action(
            action=action,
            description=description,
            user_id=user_id,
            ip_address=ip_address,
            resource_type="file",
            resource_id=str(file_id),
            severity=AuditSeverity.LOW,
            metadata={"filename": filename, "file_size": file_size}
        )
    
    async def log_permission_event(
        self,
        action: AuditAction,
        user_id: uuid.UUID,
        resource_path: str,
        permission_action: str,
        granted: bool,
        ip_address: Optional[str] = None
    ) -> AuditLog:
        """Log permission-related events."""
        
        result = "granted" if granted else "denied"
        description = f"Permission {result}: {permission_action} on {resource_path}"
        severity = AuditSeverity.LOW if granted else AuditSeverity.MEDIUM
        
        return await self.log_action(
            action=action,
            description=description,
            user_id=user_id,
            ip_address=ip_address,
            resource_path=resource_path,
            severity=severity,
            metadata={
                "permission_action": permission_action,
                "granted": granted
            }
        )
    
    async def create_security_event(
        self,
        event_type: str,
        title: str,
        description: str,
        severity: AuditSeverity,
        source_ip: Optional[str] = None,
        source_user_agent: Optional[str] = None,
        source_user_id: Optional[uuid.UUID] = None,
        detection_method: str = "automated",
        confidence_score: Optional[float] = None,
        event_data: Optional[Dict[str, Any]] = None
    ) -> SecurityEvent:
        """Create a security event."""
        
        security_event = SecurityEvent(
            event_type=event_type,
            severity=severity,
            title=title,
            description=description,
            source_ip=source_ip,
            source_user_agent=source_user_agent,
            source_user_id=source_user_id,
            detection_method=detection_method,
            confidence_score=confidence_score,
            event_data=event_data or {}
        )
        
        self.db.add(security_event)
        await self.db.flush()
        return security_event
    
    async def get_audit_logs(
        self,
        user_id: Optional[uuid.UUID] = None,
        action: Optional[AuditAction] = None,
        resource_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> list[AuditLog]:
        """Retrieve audit logs with filtering."""
        
        query = select(AuditLog).order_by(AuditLog.created_at.desc())
        
        if user_id:
            query = query.where(AuditLog.user_id == user_id)
        if action:
            query = query.where(AuditLog.action == action)
        if resource_type:
            query = query.where(AuditLog.resource_type == resource_type)
        if start_date:
            query = query.where(AuditLog.created_at >= start_date)
        if end_date:
            query = query.where(AuditLog.created_at <= end_date)
        
        query = query.limit(limit).offset(offset)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_security_events(
        self,
        event_type: Optional[str] = None,
        severity: Optional[AuditSeverity] = None,
        is_resolved: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0
    ) -> list[SecurityEvent]:
        """Retrieve security events with filtering."""
        
        query = select(SecurityEvent).order_by(SecurityEvent.detected_at.desc())
        
        if event_type:
            query = query.where(SecurityEvent.event_type == event_type)
        if severity:
            query = query.where(SecurityEvent.severity == severity)
        if is_resolved is not None:
            query = query.where(SecurityEvent.is_resolved == is_resolved)
        
        query = query.limit(limit).offset(offset)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def resolve_security_event(
        self,
        event_id: uuid.UUID,
        resolved_by_id: uuid.UUID,
        resolution_notes: str
    ) -> Optional[SecurityEvent]:
        """Resolve a security event."""
        
        query = select(SecurityEvent).where(SecurityEvent.id == event_id)
        result = await self.db.execute(query)
        event = result.scalar_one_or_none()
        
        if event:
            event.is_resolved = True
            event.resolved_at = datetime.utcnow()
            event.resolved_by_id = resolved_by_id
            event.resolution_notes = resolution_notes
            await self.db.flush()
        
        return event
    
    async def get_audit_statistics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get audit statistics for reporting."""
        
        base_query = select(AuditLog)
        
        if start_date:
            base_query = base_query.where(AuditLog.created_at >= start_date)
        if end_date:
            base_query = base_query.where(AuditLog.created_at <= end_date)
        
        # Total events
        total_query = select(func.count()).select_from(base_query.subquery())
        total_result = await self.db.execute(total_query)
        total_events = total_result.scalar()
        
        # Events by action
        action_query = select(
            AuditLog.action,
            func.count().label('count')
        ).group_by(AuditLog.action)
        
        if start_date:
            action_query = action_query.where(AuditLog.created_at >= start_date)
        if end_date:
            action_query = action_query.where(AuditLog.created_at <= end_date)
        
        action_result = await self.db.execute(action_query)
        events_by_action = {row.action: row.count for row in action_result}
        
        # Events by severity
        severity_query = select(
            AuditLog.severity,
            func.count().label('count')
        ).group_by(AuditLog.severity)
        
        if start_date:
            severity_query = severity_query.where(AuditLog.created_at >= start_date)
        if end_date:
            severity_query = severity_query.where(AuditLog.created_at <= end_date)
        
        severity_result = await self.db.execute(severity_query)
        events_by_severity = {row.severity: row.count for row in severity_result}
        
        return {
            "total_events": total_events,
            "events_by_action": events_by_action,
            "events_by_severity": events_by_severity,
            "period": {
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None
            }
        }
    
    async def get_file_audit_logs(
        self,
        file_id: uuid.UUID,
        limit: int = 100
    ) -> list[Dict[str, Any]]:
        """Get audit logs for a specific file."""
        
        query = (
            select(AuditLog)
            .where(AuditLog.resource_id == str(file_id))
            .where(AuditLog.resource_type == "file")
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        
        result = await self.db.execute(query)
        logs = result.scalars().all()
        
        return [
            {
                "id": str(log.id),
                "action": log.action.value,
                "description": log.description,
                "user_id": str(log.user_id) if log.user_id else None,
                "ip_address": log.ip_address,
                "created_at": log.created_at.isoformat(),
                "metadata": log.custom_metadata
            }
            for log in logs
        ]