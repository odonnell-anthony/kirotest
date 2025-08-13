"""
Test suite for document revision control system.
"""
import asyncio
import uuid
import os
import sys
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Add the app directory to the path so we can import modules
sys.path.append(os.path.join(os.path.dirname(__file__), '.'))

from app.core.database import Base
from app.models.user import User, UserRole
from app.models.document import Document, DocumentStatus, ContentFormat
from app.models.revision import DocumentRevision
from app.services.document import DocumentService
from app.schemas.document import DocumentCreate, DocumentUpdate
from app.core.exceptions import NotFoundError, PermissionDeniedError


# Test database setup
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_revisions.db"

async def create_db_session():
    """Create test database session."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Create session
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        return session, engine

async def cleanup_db(engine):
    """Cleanup test database."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

async def create_test_user(db_session):
    """Create test user."""
    user = User(
        username="testuser",
        email="test@example.com",
        password_hash="hashed_password",
        role=UserRole.NORMAL
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

async def create_admin_user(db_session):
    """Create admin user."""
    user = User(
        username="admin",
        email="admin@example.com",
        password_hash="hashed_password",
        role=UserRole.ADMIN
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

async def create_test_document(db_session, test_user):
    """Create test document."""
    document = Document(
        title="Test Document",
        slug="test-document",
        content="# Initial Content\n\nThis is the initial content.",
        content_type=ContentFormat.MARKDOWN,
        folder_path="/test/",
        status=DocumentStatus.PUBLISHED,
        author_id=test_user.id
    )
    db_session.add(document)
    await db_session.commit()
    await db_session.refresh(document)
    return document


async def test_revision_created_on_update():
    """Test that a revision is created when document is updated."""
    print("Testing revision creation on document update...")
    
    db_session, engine = await create_db_session()
    try:
        test_user = await create_test_user(db_session)
        test_document = await create_test_document(db_session, test_user)
        service = DocumentService(db_session)
        
        # Update document
        update_data = DocumentUpdate(
            title="Updated Title",
            content="# Updated Content\n\nThis is updated content.",
            change_summary="Updated title and content"
        )
        
        updated_doc = await service.update_document(
            test_document.id, 
            update_data, 
            test_user,
            change_summary="Updated title and content"
        )
        
        # Check that revision was created
        revisions = await service.get_document_revisions(test_document.id, test_user)
        
        assert len(revisions) == 1, f"Expected 1 revision, got {len(revisions)}"
        assert revisions[0].revision_number == 1, f"Expected revision number 1, got {revisions[0].revision_number}"
        assert revisions[0].title == "Test Document", f"Expected original title, got {revisions[0].title}"
        assert revisions[0].content == "# Initial Content\n\nThis is the initial content.", f"Expected original content"
        assert revisions[0].change_summary == "Updated title and content", f"Expected change summary"
        assert revisions[0].author_id == test_user.id, f"Expected correct author"
        
        print("✓ Revision creation test passed")
        
    finally:
        await cleanup_db(engine)

async def test_multiple_revisions_increment_number():
    """Test that revision numbers increment correctly."""
    print("Testing revision number incrementation...")
    
    db_session, engine = await create_db_session()
    try:
        test_user = await create_test_user(db_session)
        test_document = await create_test_document(db_session, test_user)
        service = DocumentService(db_session)
        
        # First update
        update_data1 = DocumentUpdate(
            content="First update",
            change_summary="First change"
        )
        await service.update_document(test_document.id, update_data1, test_user)
        
        # Second update
        update_data2 = DocumentUpdate(
            content="Second update",
            change_summary="Second change"
        )
        await service.update_document(test_document.id, update_data2, test_user)
        
        # Check revisions
        revisions = await service.get_document_revisions(test_document.id, test_user)
        
        assert len(revisions) == 2, f"Expected 2 revisions, got {len(revisions)}"
        assert revisions[0].revision_number == 2, f"Expected revision 2 first, got {revisions[0].revision_number}"
        assert revisions[1].revision_number == 1, f"Expected revision 1 second, got {revisions[1].revision_number}"
        assert revisions[0].change_summary == "Second change", f"Expected second change summary"
        assert revisions[1].change_summary == "First change", f"Expected first change summary"
        
        print("✓ Revision incrementation test passed")
        
    finally:
        await cleanup_db(engine)

async def test_get_specific_revision():
    """Test getting a specific revision."""
    print("Testing specific revision retrieval...")
    
    db_session, engine = await create_db_session()
    try:
        test_user = await create_test_user(db_session)
        test_document = await create_test_document(db_session, test_user)
        service = DocumentService(db_session)
        
        # Update document to create revision
        update_data = DocumentUpdate(
            title="New Title",
            content="New content",
            change_summary="Major update"
        )
        await service.update_document(test_document.id, update_data, test_user)
        
        # Get specific revision
        revision = await service.get_document_revision(test_document.id, 1, test_user)
        
        assert revision.revision_number == 1, f"Expected revision 1, got {revision.revision_number}"
        assert revision.title == "Test Document", f"Expected original title, got {revision.title}"
        assert revision.content == "# Initial Content\n\nThis is the initial content.", f"Expected original content"
        assert revision.change_summary == "Major update", f"Expected change summary"
        
        print("✓ Specific revision retrieval test passed")
        
    finally:
        await cleanup_db(engine)

async def test_restore_revision():
    """Test restoring document to previous revision."""
    print("Testing revision restoration...")
    
    db_session, engine = await create_db_session()
    try:
        test_user = await create_test_user(db_session)
        test_document = await create_test_document(db_session, test_user)
        service = DocumentService(db_session)
        
        # Update document multiple times
        update_data1 = DocumentUpdate(
            title="Version 1",
            content="Content version 1",
            change_summary="First update"
        )
        await service.update_document(test_document.id, update_data1, test_user)
        
        update_data2 = DocumentUpdate(
            title="Version 2", 
            content="Content version 2",
            change_summary="Second update"
        )
        await service.update_document(test_document.id, update_data2, test_user)
        
        # Restore to revision 1 (original state)
        restored_doc = await service.restore_document_revision(
            test_document.id, 
            1, 
            test_user,
            change_summary="Restored to original"
        )
        
        # Check document was restored
        assert restored_doc.title == "Test Document", f"Expected original title, got {restored_doc.title}"
        assert restored_doc.content == "# Initial Content\n\nThis is the initial content.", f"Expected original content"
        
        # Check that restoration created a new revision
        revisions = await service.get_document_revisions(test_document.id, test_user)
        assert len(revisions) == 3, f"Expected 3 revisions after restoration, got {len(revisions)}"
        assert revisions[0].change_summary == "Restored to original", f"Expected restoration summary"
        
        print("✓ Revision restoration test passed")
        
    finally:
        await cleanup_db(engine)

async def test_compare_revisions():
    """Test comparing two document revisions."""
    print("Testing revision comparison...")
    
    db_session, engine = await create_db_session()
    try:
        test_user = await create_test_user(db_session)
        test_document = await create_test_document(db_session, test_user)
        service = DocumentService(db_session)
        
        # Create revisions by updating document
        update_data1 = DocumentUpdate(
            title="Updated Title",
            content="Updated content",
            change_summary="First update"
        )
        await service.update_document(test_document.id, update_data1, test_user)
        
        update_data2 = DocumentUpdate(
            title="Final Title",
            content="Final content", 
            change_summary="Second update"
        )
        await service.update_document(test_document.id, update_data2, test_user)
        
        # Compare revisions 1 and 2
        comparison = await service.compare_document_revisions(
            test_document.id, 1, 2, test_user
        )
        
        assert comparison["document_id"] == str(test_document.id), f"Expected correct document ID"
        assert comparison["revision1"]["number"] == 1, f"Expected revision 1"
        assert comparison["revision2"]["number"] == 2, f"Expected revision 2"
        assert comparison["revision1"]["title"] == "Test Document", f"Expected original title in revision 1"
        assert comparison["revision2"]["title"] == "Updated Title", f"Expected updated title in revision 2"
        assert comparison["changes"]["title_changed"] is True, f"Expected title change detected"
        assert comparison["changes"]["content_changed"] is True, f"Expected content change detected"
        
        print("✓ Revision comparison test passed")
        
    finally:
        await cleanup_db(engine)

async def test_revision_author_tracking():
    """Test that revisions track the correct author."""
    print("Testing revision author tracking...")
    
    db_session, engine = await create_db_session()
    try:
        test_user = await create_test_user(db_session)
        admin_user = await create_admin_user(db_session)
        test_document = await create_test_document(db_session, test_user)
        service = DocumentService(db_session)
        
        # User updates document
        update_data1 = DocumentUpdate(
            content="User update",
            change_summary="Updated by user"
        )
        await service.update_document(test_document.id, update_data1, test_user)
        
        # Admin updates document
        update_data2 = DocumentUpdate(
            content="Admin update", 
            change_summary="Updated by admin"
        )
        await service.update_document(test_document.id, update_data2, admin_user)
        
        # Check revision authors
        revisions = await service.get_document_revisions(test_document.id, admin_user)
        
        assert len(revisions) == 2, f"Expected 2 revisions, got {len(revisions)}"
        assert revisions[0].author_id == test_user.id, f"Expected first revision by test user"
        assert revisions[1].author_id == admin_user.id, f"Expected second revision by admin"
        
        print("✓ Revision author tracking test passed")
        
    finally:
        await cleanup_db(engine)

async def run_all_tests():
    """Run all revision system tests."""
    print("Starting revision control system tests...\n")
    
    try:
        await test_revision_created_on_update()
        await test_multiple_revisions_increment_number()
        await test_get_specific_revision()
        await test_restore_revision()
        await test_compare_revisions()
        await test_revision_author_tracking()
        
        print("\n🎉 All revision control system tests passed!")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    # Run tests
    success = asyncio.run(run_all_tests())