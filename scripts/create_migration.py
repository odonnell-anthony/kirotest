#!/usr/bin/env python3
"""
Script to create Alembic migration with indexes and performance optimizations.
"""
import os
import sys

# Add the app directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from alembic.config import Config
from alembic import command


def create_migration():
    """Create a new Alembic migration."""
    # Set up Alembic configuration
    alembic_cfg = Config("alembic.ini")
    
    # Create the migration
    command.revision(
        alembic_cfg, 
        autogenerate=True, 
        message="Add database indexes and performance optimizations"
    )
    print("Migration created successfully!")


if __name__ == "__main__":
    create_migration()