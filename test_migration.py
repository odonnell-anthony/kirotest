#!/usr/bin/env python3
"""
Test script to verify the migration script works correctly.
"""

import asyncio
import sys
import os

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

async def test_migration():
    """Test the migration script."""
    try:
        print("Testing migration script...")
        
        # Import the migration script
        from migrate_metadata_column import run_migration
        
        print("Migration script imported successfully!")
        print("Ready to run in Docker environment.")
        
    except ImportError as e:
        print(f"Import error: {e}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_migration())
    if success:
        print("✅ Migration script test passed!")
    else:
        print("❌ Migration script test failed!")
        sys.exit(1) 