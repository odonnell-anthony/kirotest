#!/usr/bin/env python3
"""
Script to rename metadata column to custom_metadata in all relevant tables.
This fixes the SQLAlchemy reserved word issue.
"""

import asyncio
import asyncpg
import os
import sys
from typing import Optional

async def run_migration():
    """Run the migration to rename metadata columns."""
    
    # Get database connection details from environment
    # Support both direct environment variables and DATABASE_URL parsing
    db_url = os.getenv('DATABASE_URL')
    
    if db_url:
        # Parse DATABASE_URL format: postgresql+asyncpg://user:pass@host:port/db
        if db_url.startswith('postgresql+asyncpg://'):
            db_url = db_url.replace('postgresql+asyncpg://', 'postgresql://')
        
        # Extract components from URL
        if db_url.startswith('postgresql://'):
            parts = db_url.replace('postgresql://', '').split('@')
            if len(parts) == 2:
                auth_part, host_part = parts
                user_pass = auth_part.split(':')
                if len(user_pass) == 2:
                    db_user, db_password = user_pass
                else:
                    db_user = user_pass[0]
                    db_password = ''
                
                host_port_db = host_part.split('/')
                if len(host_port_db) == 2:
                    host_port, db_name = host_port_db
                    host_port_parts = host_port.split(':')
                    if len(host_port_parts) == 2:
                        db_host, db_port = host_port_parts
                        db_port = int(db_port)
                    else:
                        db_host = host_port_parts[0]
                        db_port = 5432
                else:
                    db_host = 'localhost'
                    db_port = 5432
                    db_name = 'wiki'
            else:
                db_host = 'localhost'
                db_port = 5432
                db_name = 'wiki'
                db_user = 'wiki'
                db_password = 'wiki'
        else:
            db_host = 'localhost'
            db_port = 5432
            db_name = 'wiki'
            db_user = 'wiki'
            db_password = 'wiki'
    else:
        # Fallback to individual environment variables
        db_host = os.getenv('DB_HOST', 'db')  # Default to 'db' for Docker service name
        db_port = int(os.getenv('DB_PORT', '5432'))
        db_name = os.getenv('DB_NAME', 'wiki')
        db_user = os.getenv('DB_USER', 'wiki')
        db_password = os.getenv('DB_PASSWORD', 'wiki')
    
    try:
        # Connect to database
        print(f"Connecting to database {db_name} on {db_host}:{db_port}...")
        conn = await asyncpg.connect(
            host=db_host,
            port=db_port,
            database=db_name,
            user=db_user,
            password=db_password
        )
        
        print("Connected successfully!")
        
        # Check if metadata column exists in each table
        tables = ['documents', 'document_revisions', 'audit_logs']
        
        for table in tables:
            # Check if table exists
            table_exists = await conn.fetchval(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = $1)",
                table
            )
            
            if not table_exists:
                print(f"Table {table} does not exist, skipping...")
                continue
            
            # Check if metadata column exists
            column_exists = await conn.fetchval(
                "SELECT EXISTS (SELECT FROM information_schema.columns WHERE table_name = $1 AND column_name = 'metadata')",
                table
            )
            
            if not column_exists:
                print(f"Column 'metadata' does not exist in table {table}, skipping...")
                continue
            
            # Check if custom_metadata column already exists
            custom_column_exists = await conn.fetchval(
                "SELECT EXISTS (SELECT FROM information_schema.columns WHERE table_name = $1 AND column_name = 'custom_metadata')",
                table
            )
            
            if custom_column_exists:
                print(f"Column 'custom_metadata' already exists in table {table}, skipping...")
                continue
            
            # Rename the column
            print(f"Renaming 'metadata' to 'custom_metadata' in table {table}...")
            await conn.execute(f"ALTER TABLE {table} RENAME COLUMN metadata TO custom_metadata")
            
            # Add comment
            await conn.execute(f"""
                COMMENT ON COLUMN {table}.custom_metadata IS 
                'Custom metadata for {table} (renamed from metadata to avoid SQLAlchemy reserved word conflict)'
            """)
            
            print(f"Successfully renamed column in table {table}")
        
        print("\nMigration completed successfully!")
        
    except Exception as e:
        print(f"Error during migration: {e}")
        # In Docker, we want to exit with error code so the container fails
        sys.exit(1)
    finally:
        if 'conn' in locals():
            await conn.close()

if __name__ == "__main__":
    asyncio.run(run_migration()) 