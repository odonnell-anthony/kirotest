#!/usr/bin/env python3
"""
Data retention script for compliance and cleanup.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta

# Add the app directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.database import engine, AsyncSessionLocal
from app.models.audit import AuditLog, SecurityEvent, DataRetentionPolicy
from sqlalchemy import select, delete, func


async def apply_retention_policies():
    """Apply data retention policies to clean up old data."""
    print("Applying data retention policies...")
    
    async with AsyncSessionLocal() as db:
        # Get all active retention policies
        query = select(DataRetentionPolicy).where(DataRetentionPolicy.is_active == True)
        result = await db.execute(query)
        policies = result.scalars().all()
        
        if not policies:
            print("No active retention policies found")
            return
        
        for policy in policies:
            print(f"Applying policy: {policy.name}")
            
            # Calculate cutoff date
            cutoff_date = datetime.utcnow() - timedelta(days=policy.retention_days)
            
            if policy.table_name == "audit_logs":
                # Delete old audit logs
                delete_query = delete(AuditLog).where(AuditLog.created_at < cutoff_date)
                result = await db.execute(delete_query)
                deleted_count = result.rowcount
                print(f"  Deleted {deleted_count} audit logs older than {cutoff_date}")
            
            elif policy.table_name == "security_events":
                # Delete old resolved security events
                delete_query = delete(SecurityEvent).where(
                    SecurityEvent.detected_at < cutoff_date,
                    SecurityEvent.is_resolved == True
                )
                result = await db.execute(delete_query)
                deleted_count = result.rowcount
                print(f"  Deleted {deleted_count} resolved security events older than {cutoff_date}")
        
        await db.commit()
        print("Data retention policies applied successfully!")


async def create_default_retention_policies():
    """Create default data retention policies."""
    print("Creating default data retention policies...")
    
    async with AsyncSessionLocal() as db:
        # Check if policies already exist
        query = select(func.count()).select_from(DataRetentionPolicy)
        result = await db.execute(query)
        count = result.scalar()
        
        if count > 0:
            print("Retention policies already exist")
            return
        
        # Create default policies
        policies = [
            DataRetentionPolicy(
                name="Audit Logs Retention",
                description="Retain audit logs for 2 years for compliance",
                table_name="audit_logs",
                retention_days=730,  # 2 years
                is_active=True
            ),
            DataRetentionPolicy(
                name="Security Events Retention",
                description="Retain resolved security events for 1 year",
                table_name="security_events",
                retention_days=365,  # 1 year
                is_active=True
            ),
            DataRetentionPolicy(
                name="Document Revisions Retention",
                description="Retain document revisions for 5 years",
                table_name="document_revisions",
                retention_days=1825,  # 5 years
                is_active=False  # Disabled by default, enable as needed
            )
        ]
        
        for policy in policies:
            db.add(policy)
        
        await db.commit()
        print(f"Created {len(policies)} default retention policies")


async def get_retention_statistics():
    """Get statistics about data that would be affected by retention policies."""
    print("Calculating retention statistics...")
    
    async with AsyncSessionLocal() as db:
        # Get audit log statistics
        audit_query = select(
            func.count().label('total'),
            func.min(AuditLog.created_at).label('oldest'),
            func.max(AuditLog.created_at).label('newest')
        )
        result = await db.execute(audit_query)
        audit_stats = result.first()
        
        if audit_stats.total > 0:
            print(f"Audit Logs: {audit_stats.total} records")
            print(f"  Oldest: {audit_stats.oldest}")
            print(f"  Newest: {audit_stats.newest}")
        else:
            print("Audit Logs: No records found")
        
        # Get security event statistics
        security_query = select(
            func.count().label('total'),
            func.count().filter(SecurityEvent.is_resolved == True).label('resolved'),
            func.min(SecurityEvent.detected_at).label('oldest'),
            func.max(SecurityEvent.detected_at).label('newest')
        )
        result = await db.execute(security_query)
        security_stats = result.first()
        
        if security_stats.total > 0:
            print(f"Security Events: {security_stats.total} records ({security_stats.resolved} resolved)")
            print(f"  Oldest: {security_stats.oldest}")
            print(f"  Newest: {security_stats.newest}")
        else:
            print("Security Events: No records found")


async def main():
    """Main retention function."""
    try:
        if len(sys.argv) > 1:
            command = sys.argv[1]
            
            if command == "apply":
                await apply_retention_policies()
            elif command == "init":
                await create_default_retention_policies()
            elif command == "stats":
                await get_retention_statistics()
            else:
                print("Usage: python data_retention.py [apply|init|stats]")
                print("  apply - Apply retention policies and delete old data")
                print("  init  - Create default retention policies")
                print("  stats - Show retention statistics")
        else:
            print("Usage: python data_retention.py [apply|init|stats]")
    
    except Exception as e:
        print(f"Retention operation failed: {e}")
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())