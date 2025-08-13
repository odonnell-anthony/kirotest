"""add_file_security_fields

Revision ID: 002_add_file_security_fields
Revises: 001_add_indexes_and_optimizations
Create Date: 2024-01-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002_add_file_security_fields'
down_revision = '001_add_indexes_and_optimizations'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add security and audit fields to files table
    op.add_column('files', sa.Column('is_malware_scanned', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('files', sa.Column('malware_scan_result', sa.String(length=50), nullable=True))
    op.add_column('files', sa.Column('access_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('files', sa.Column('last_accessed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Remove security and audit fields from files table
    op.drop_column('files', 'last_accessed_at')
    op.drop_column('files', 'access_count')
    op.drop_column('files', 'malware_scan_result')
    op.drop_column('files', 'is_malware_scanned')