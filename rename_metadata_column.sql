-- SQL script to rename metadata column to custom_metadata
-- This fixes the SQLAlchemy reserved word issue

-- Rename metadata column in documents table
ALTER TABLE documents RENAME COLUMN metadata TO custom_metadata;

-- Rename metadata column in document_revisions table  
ALTER TABLE document_revisions RENAME COLUMN metadata TO custom_metadata;

-- Rename metadata column in audit_logs table
ALTER TABLE audit_logs RENAME COLUMN metadata TO custom_metadata;

-- Add comment to document the change
COMMENT ON COLUMN documents.custom_metadata IS 'Custom metadata for documents (renamed from metadata to avoid SQLAlchemy reserved word conflict)';
COMMENT ON COLUMN document_revisions.custom_metadata IS 'Custom metadata for document revisions (renamed from metadata to avoid SQLAlchemy reserved word conflict)';
COMMENT ON COLUMN audit_logs.custom_metadata IS 'Custom metadata for audit logs (renamed from metadata to avoid SQLAlchemy reserved word conflict)'; 