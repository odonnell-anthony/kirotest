#!/usr/bin/env python3
"""
Database migration script for the wiki application.
"""
import asyncio
import os
import sys

# Add the app directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.database import engine, Base
from app.core.config import settings
import app.models  # Import all models


async def create_tables():
    """Create all database tables."""
    print("Creating database tables...")
    
    async with engine.begin() as conn:
        # Drop all tables (for development)
        await conn.run_sync(Base.metadata.drop_all)
        print("Dropped existing tables")
        
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        print("Created all tables")
    
    print("Database migration completed successfully!")


async def main():
    """Main migration function."""
    try:
        await create_tables()
    except Exception as e:
        print(f"Migration failed: {e}")
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())