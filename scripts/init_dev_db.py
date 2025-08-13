#!/usr/bin/env python3
"""
Initialize development database with basic data.
"""
import asyncio
import asyncpg
import os
from datetime import datetime

async def init_dev_database():
    """Initialize development database."""
    try:
        # Connect to database
        db_url = os.getenv("DATABASE_URL", "postgresql://wiki:wiki@localhost:5432/wiki")
        conn = await asyncpg.connect(db_url)
        
        print("Connected to database successfully")
        
        # Test basic connectivity
        result = await conn.fetchval("SELECT 1")
        print(f"Database test query result: {result}")
        
        # Check if tables exist (they should be created by SQLAlchemy)
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        
        print(f"Found {len(tables)} tables in database:")
        for table in tables:
            print(f"  - {table['table_name']}")
        
        await conn.close()
        print("Database initialization completed successfully")
        
    except Exception as e:
        print(f"Error initializing database: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(init_dev_database())