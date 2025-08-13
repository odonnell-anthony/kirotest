"""Add database indexes and performance optimizations

Revision ID: 001
Revises: 
Create Date: 2024-01-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_add_indexes_and_optimizations'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add performance indexes and optimizations."""
    
    # Enable required PostgreSQL extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gin")
    
    # Full-text search indexes for documents
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_search 
        ON documents USING GIN(search_vector)
    """)
    
    # Trigram indexes for tag autocomplete functionality
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_tags_name_trgm 
        ON tags USING GIN(name gin_trgm_ops)
    """)
    
    # Performance indexes on frequently queried columns
    
    # Document indexes
    op.create_index('idx_documents_folder_path', 'documents', ['folder_path'])
    op.create_index('idx_documents_status', 'documents', ['status'])
    op.create_index('idx_documents_updated_at_desc', 'documents', [sa.text('updated_at DESC')])
    op.create_index('idx_documents_author_id', 'documents', ['author_id'])
    op.create_index('idx_documents_published_at', 'documents', ['published_at'])
    
    # User indexes
    op.create_index('idx_users_username', 'users', ['username'])
    op.create_index('idx_users_email', 'users', ['email'])
    op.create_index('idx_users_role', 'users', ['role'])
    op.create_index('idx_users_is_active', 'users', ['is_active'])
    
    # Folder indexes
    op.create_index('idx_folders_path', 'folders', ['path'])
    op.create_index('idx_folders_parent_path', 'folders', ['parent_path'])
    
    # Tag indexes
    op.create_index('idx_tags_name', 'tags', ['name'])
    op.create_index('idx_tags_usage_count_desc', 'tags', [sa.text('usage_count DESC')])
    
    # Document-Tag association indexes
    op.create_index('idx_document_tags_tag_id', 'document_tags', ['tag_id'])
    op.create_index('idx_document_tags_document_id', 'document_tags', ['document_id'])
    
    # Comment indexes
    op.create_index('idx_comments_document_created', 'comments', ['document_id', 'created_at'])
    op.create_index('idx_comments_author_id', 'comments', ['author_id'])
    op.create_index('idx_comments_parent_id', 'comments', ['parent_id'])
    
    # File indexes
    op.create_index('idx_files_path', 'files', ['file_path'])
    op.create_index('idx_files_document_id', 'files', ['document_id'])
    op.create_index('idx_files_checksum', 'files', ['checksum'])
    op.create_index('idx_files_uploaded_by', 'files', ['uploaded_by_id'])
    
    # Document revision indexes
    op.create_index('idx_revisions_document_revision_desc', 'document_revisions', 
                   ['document_id', sa.text('revision_number DESC')])
    op.create_index('idx_revisions_author_id', 'document_revisions', ['author_id'])
    
    # Permission indexes
    op.create_index('idx_permissions_group_id', 'permissions', ['group_id'])
    op.create_index('idx_permissions_resource_pattern', 'permissions', ['resource_pattern'])
    op.create_index('idx_permissions_action', 'permissions', ['action'])
    
    # User-Group association indexes
    op.create_index('idx_user_groups_user_id', 'user_groups', ['user_id'])
    op.create_index('idx_user_groups_group_id', 'user_groups', ['group_id'])
    
    # Composite indexes for common query patterns
    op.create_index('idx_documents_status_folder', 'documents', ['status', 'folder_path'])
    op.create_index('idx_documents_author_status', 'documents', ['author_id', 'status'])
    op.create_index('idx_comments_document_not_deleted', 'comments', 
                   ['document_id', 'is_deleted', 'created_at'])
    
    # Partial indexes for better performance
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_published 
        ON documents (updated_at DESC) 
        WHERE status = 'published'
    """)
    
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_active 
        ON users (username) 
        WHERE is_active = true
    """)
    
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_comments_not_deleted 
        ON comments (document_id, created_at) 
        WHERE is_deleted = false
    """)


def downgrade() -> None:
    """Remove performance indexes and optimizations."""
    
    # Drop custom indexes
    op.drop_index('idx_documents_search', table_name='documents')
    op.drop_index('idx_tags_name_trgm', table_name='tags')
    
    # Drop standard indexes
    op.drop_index('idx_documents_folder_path', table_name='documents')
    op.drop_index('idx_documents_status', table_name='documents')
    op.drop_index('idx_documents_updated_at_desc', table_name='documents')
    op.drop_index('idx_documents_author_id', table_name='documents')
    op.drop_index('idx_documents_published_at', table_name='documents')
    
    op.drop_index('idx_users_username', table_name='users')
    op.drop_index('idx_users_email', table_name='users')
    op.drop_index('idx_users_role', table_name='users')
    op.drop_index('idx_users_is_active', table_name='users')
    
    op.drop_index('idx_folders_path', table_name='folders')
    op.drop_index('idx_folders_parent_path', table_name='folders')
    
    op.drop_index('idx_tags_name', table_name='tags')
    op.drop_index('idx_tags_usage_count_desc', table_name='tags')
    
    op.drop_index('idx_document_tags_tag_id', table_name='document_tags')
    op.drop_index('idx_document_tags_document_id', table_name='document_tags')
    
    op.drop_index('idx_comments_document_created', table_name='comments')
    op.drop_index('idx_comments_author_id', table_name='comments')
    op.drop_index('idx_comments_parent_id', table_name='comments')
    
    op.drop_index('idx_files_path', table_name='files')
    op.drop_index('idx_files_document_id', table_name='files')
    op.drop_index('idx_files_checksum', table_name='files')
    op.drop_index('idx_files_uploaded_by', table_name='files')
    
    op.drop_index('idx_revisions_document_revision_desc', table_name='document_revisions')
    op.drop_index('idx_revisions_author_id', table_name='document_revisions')
    
    op.drop_index('idx_permissions_group_id', table_name='permissions')
    op.drop_index('idx_permissions_resource_pattern', table_name='permissions')
    op.drop_index('idx_permissions_action', table_name='permissions')
    
    op.drop_index('idx_user_groups_user_id', table_name='user_groups')
    op.drop_index('idx_user_groups_group_id', table_name='user_groups')
    
    op.drop_index('idx_documents_status_folder', table_name='documents')
    op.drop_index('idx_documents_author_status', table_name='documents')
    op.drop_index('idx_comments_document_not_deleted', table_name='comments')
    
    # Drop partial indexes
    op.execute("DROP INDEX IF EXISTS idx_documents_published")
    op.execute("DROP INDEX IF EXISTS idx_users_active")
    op.execute("DROP INDEX IF EXISTS idx_comments_not_deleted")