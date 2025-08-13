"""
Integration tests for database operations.
"""
import pytest
import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole
from app.models.document import Document, DocumentStatus
from app.models.folder import Folder
from app.models.tag import Tag, DocumentTag
from app.models.revision import DocumentRevision
from app.models.permission import PermissionGroup, Permission, UserGroup
from tests.conftest import UserFactory, DocumentFactory, TagFactory


@pytest.mark.integration
class TestUserDatabaseOperations:
    """Test user-related database operations."""
    
    @pytest.mark.asyncio
    async def test_create_user(self, test_db: AsyncSession):
        """Test creating a user in the database."""
        user = UserFactory.create_user(
            username="testuser",
            email="test@example.com",
            role=UserRole.NORMAL
        )
        
        test_db.add(user)
        await test_db.commit()
        await test_db.refresh(user)
        
        # Verify user was created
        assert user.id is not None
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.role == UserRole.NORMAL
        assert user.is_active is True
        assert user.created_at is not None
    
    @pytest.mark.asyncio
    async def test_query_user_by_username(self, test_db: AsyncSession):
        """Test querying user by username."""
        # Create user
        user = UserFactory.create_user(username="querytest")
        test_db.add(user)
        await test_db.commit()
        
        # Query user
        stmt = select(User).where(User.username == "querytest")
        result = await test_db.execute(stmt)
        found_user = result.scalar_one_or_none()
        
        assert found_user is not None
        assert found_user.username == "querytest"
        assert found_user.id == user.id
    
    @pytest.mark.asyncio
    async def test_query_user_by_email(self, test_db: AsyncSession):
        """Test querying user by email."""
        # Create user
        user = UserFactory.create_user(email="query@test.com")
        test_db.add(user)
        await test_db.commit()
        
        # Query user
        stmt = select(User).where(User.email == "query@test.com")
        result = await test_db.execute(stmt)
        found_user = result.scalar_one_or_none()
        
        assert found_user is not None
        assert found_user.email == "query@test.com"
        assert found_user.id == user.id
    
    @pytest.mark.asyncio
    async def test_update_user_last_login(self, test_db: AsyncSession):
        """Test updating user's last login timestamp."""
        from datetime import datetime
        
        # Create user
        user = UserFactory.create_user()
        test_db.add(user)
        await test_db.commit()
        
        # Update last login
        user.last_login_at = datetime.utcnow()
        await test_db.commit()
        await test_db.refresh(user)
        
        assert user.last_login_at is not None
        assert isinstance(user.last_login_at, datetime)


@pytest.mark.integration
class TestDocumentDatabaseOperations:
    """Test document-related database operations."""
    
    @pytest.mark.asyncio
    async def test_create_document(self, test_db: AsyncSession, test_user: User):
        """Test creating a document in the database."""
        document = DocumentFactory.create_document(
            title="Test Document",
            content="# Test Content",
            author_id=test_user.id,
            folder_path="/test/",
            status=DocumentStatus.PUBLISHED
        )
        
        test_db.add(document)
        await test_db.commit()
        await test_db.refresh(document)
        
        # Verify document was created
        assert document.id is not None
        assert document.title == "Test Document"
        assert document.content == "# Test Content"
        assert document.author_id == test_user.id
        assert document.folder_path == "/test/"
        assert document.status == DocumentStatus.PUBLISHED
        assert document.created_at is not None
        assert document.updated_at is not None
    
    @pytest.mark.asyncio
    async def test_query_documents_by_folder(self, test_db: AsyncSession, test_user: User):
        """Test querying documents by folder path."""
        folder_path = "/test-folder/"
        
        # Create documents in specific folder
        for i in range(3):
            document = DocumentFactory.create_document(
                title=f"Document {i}",
                folder_path=folder_path,
                author_id=test_user.id
            )
            test_db.add(document)
        
        await test_db.commit()
        
        # Query documents by folder
        stmt = select(Document).where(Document.folder_path == folder_path)
        result = await test_db.execute(stmt)
        documents = result.scalars().all()
        
        assert len(documents) == 3
        assert all(doc.folder_path == folder_path for doc in documents)
    
    @pytest.mark.asyncio
    async def test_query_documents_by_author(self, test_db: AsyncSession, test_user: User):
        """Test querying documents by author."""
        # Create documents by specific author
        for i in range(2):
            document = DocumentFactory.create_document(
                title=f"Author Document {i}",
                author_id=test_user.id
            )
            test_db.add(document)
        
        await test_db.commit()
        
        # Query documents by author
        stmt = select(Document).where(Document.author_id == test_user.id)
        result = await test_db.execute(stmt)
        documents = result.scalars().all()
        
        assert len(documents) >= 2  # At least 2, might be more from other tests
        assert all(doc.author_id == test_user.id for doc in documents)
    
    @pytest.mark.asyncio
    async def test_query_documents_by_status(self, test_db: AsyncSession, test_user: User):
        """Test querying documents by status."""
        # Create published and draft documents
        published_doc = DocumentFactory.create_document(
            title="Published Document",
            status=DocumentStatus.PUBLISHED,
            author_id=test_user.id
        )
        draft_doc = DocumentFactory.create_document(
            title="Draft Document",
            status=DocumentStatus.DRAFT,
            author_id=test_user.id
        )
        
        test_db.add(published_doc)
        test_db.add(draft_doc)
        await test_db.commit()
        
        # Query published documents
        stmt = select(Document).where(Document.status == DocumentStatus.PUBLISHED)
        result = await test_db.execute(stmt)
        published_docs = result.scalars().all()
        
        # Query draft documents
        stmt = select(Document).where(Document.status == DocumentStatus.DRAFT)
        result = await test_db.execute(stmt)
        draft_docs = result.scalars().all()
        
        assert len(published_docs) >= 1
        assert len(draft_docs) >= 1
        assert all(doc.status == DocumentStatus.PUBLISHED for doc in published_docs)
        assert all(doc.status == DocumentStatus.DRAFT for doc in draft_docs)
    
    @pytest.mark.asyncio
    async def test_document_full_text_search(self, test_db: AsyncSession, test_user: User):
        """Test full-text search on documents."""
        # Create documents with searchable content
        doc1 = DocumentFactory.create_document(
            title="Python Programming Guide",
            content="# Python Programming\n\nLearn Python programming language.",
            author_id=test_user.id
        )
        doc2 = DocumentFactory.create_document(
            title="JavaScript Tutorial",
            content="# JavaScript\n\nLearn JavaScript programming.",
            author_id=test_user.id
        )
        
        test_db.add(doc1)
        test_db.add(doc2)
        await test_db.commit()
        
        # Search for "Python"
        stmt = select(Document).where(
            Document.search_vector.match("Python")
        )
        result = await test_db.execute(stmt)
        python_docs = result.scalars().all()
        
        # Should find the Python document
        assert len(python_docs) >= 1
        assert any("Python" in doc.title or "Python" in doc.content for doc in python_docs)


@pytest.mark.integration
class TestTagDatabaseOperations:
    """Test tag-related database operations."""
    
    @pytest.mark.asyncio
    async def test_create_tag(self, test_db: AsyncSession):
        """Test creating a tag in the database."""
        tag = TagFactory.create_tag(
            name="python",
            description="Python programming language",
            color="#3776ab"
        )
        
        test_db.add(tag)
        await test_db.commit()
        await test_db.refresh(tag)
        
        # Verify tag was created
        assert tag.id is not None
        assert tag.name == "python"
        assert tag.description == "Python programming language"
        assert tag.color == "#3776ab"
        assert tag.usage_count == 0
        assert tag.created_at is not None
    
    @pytest.mark.asyncio
    async def test_document_tag_association(self, test_db: AsyncSession, test_user: User):
        """Test associating tags with documents."""
        # Create document and tag
        document = DocumentFactory.create_document(author_id=test_user.id)
        tag = TagFactory.create_tag(name="test-tag")
        
        test_db.add(document)
        test_db.add(tag)
        await test_db.commit()
        
        # Create association
        doc_tag = DocumentTag(document_id=document.id, tag_id=tag.id)
        test_db.add(doc_tag)
        await test_db.commit()
        
        # Query document with tags
        stmt = select(Document).where(Document.id == document.id)
        result = await test_db.execute(stmt)
        doc_with_tags = result.scalar_one()
        
        # Verify association exists
        stmt = select(DocumentTag).where(
            DocumentTag.document_id == document.id,
            DocumentTag.tag_id == tag.id
        )
        result = await test_db.execute(stmt)
        association = result.scalar_one_or_none()
        
        assert association is not None
        assert association.document_id == document.id
        assert association.tag_id == tag.id
    
    @pytest.mark.asyncio
    async def test_tag_usage_count_update(self, test_db: AsyncSession, test_user: User):
        """Test updating tag usage count."""
        # Create tag and documents
        tag = TagFactory.create_tag(name="popular-tag", usage_count=0)
        test_db.add(tag)
        await test_db.commit()
        
        # Create multiple documents with this tag
        for i in range(3):
            document = DocumentFactory.create_document(
                title=f"Document {i}",
                author_id=test_user.id
            )
            test_db.add(document)
            await test_db.commit()
            
            # Associate tag with document
            doc_tag = DocumentTag(document_id=document.id, tag_id=tag.id)
            test_db.add(doc_tag)
        
        await test_db.commit()
        
        # Update tag usage count
        stmt = select(func.count(DocumentTag.document_id)).where(DocumentTag.tag_id == tag.id)
        result = await test_db.execute(stmt)
        usage_count = result.scalar()
        
        tag.usage_count = usage_count
        await test_db.commit()
        await test_db.refresh(tag)
        
        assert tag.usage_count == 3


@pytest.mark.integration
class TestRevisionDatabaseOperations:
    """Test revision-related database operations."""
    
    @pytest.mark.asyncio
    async def test_create_revision(self, test_db: AsyncSession, test_user: User, test_document: Document):
        """Test creating a document revision."""
        revision = DocumentRevision(
            document_id=test_document.id,
            revision_number=1,
            title=test_document.title,
            content=test_document.content,
            author_id=test_user.id,
            change_summary="Initial revision"
        )
        
        test_db.add(revision)
        await test_db.commit()
        await test_db.refresh(revision)
        
        # Verify revision was created
        assert revision.id is not None
        assert revision.document_id == test_document.id
        assert revision.revision_number == 1
        assert revision.title == test_document.title
        assert revision.content == test_document.content
        assert revision.author_id == test_user.id
        assert revision.change_summary == "Initial revision"
        assert revision.created_at is not None
    
    @pytest.mark.asyncio
    async def test_query_revisions_by_document(self, test_db: AsyncSession, test_user: User, test_document: Document):
        """Test querying revisions by document."""
        # Create multiple revisions
        for i in range(3):
            revision = DocumentRevision(
                document_id=test_document.id,
                revision_number=i + 1,
                title=f"Title v{i + 1}",
                content=f"Content v{i + 1}",
                author_id=test_user.id,
                change_summary=f"Revision {i + 1}"
            )
            test_db.add(revision)
        
        await test_db.commit()
        
        # Query revisions by document
        stmt = select(DocumentRevision).where(
            DocumentRevision.document_id == test_document.id
        ).order_by(DocumentRevision.revision_number.desc())
        result = await test_db.execute(stmt)
        revisions = result.scalars().all()
        
        assert len(revisions) == 3
        assert all(rev.document_id == test_document.id for rev in revisions)
        assert revisions[0].revision_number == 3  # Newest first
        assert revisions[2].revision_number == 1  # Oldest last


@pytest.mark.integration
class TestPermissionDatabaseOperations:
    """Test permission-related database operations."""
    
    @pytest.mark.asyncio
    async def test_create_permission_group(self, test_db: AsyncSession):
        """Test creating a permission group."""
        group = PermissionGroup(
            name="editors",
            description="Content editors group"
        )
        
        test_db.add(group)
        await test_db.commit()
        await test_db.refresh(group)
        
        # Verify group was created
        assert group.id is not None
        assert group.name == "editors"
        assert group.description == "Content editors group"
        assert group.created_at is not None
    
    @pytest.mark.asyncio
    async def test_create_permission(self, test_db: AsyncSession):
        """Test creating a permission."""
        from app.models.permission import PermissionAction, PermissionEffect
        
        # Create group first
        group = PermissionGroup(name="test-group")
        test_db.add(group)
        await test_db.commit()
        
        # Create permission
        permission = Permission(
            group_id=group.id,
            resource_pattern="/docs/*",
            action=PermissionAction.READ_PAGES,
            effect=PermissionEffect.ALLOW
        )
        
        test_db.add(permission)
        await test_db.commit()
        await test_db.refresh(permission)
        
        # Verify permission was created
        assert permission.id is not None
        assert permission.group_id == group.id
        assert permission.resource_pattern == "/docs/*"
        assert permission.action == PermissionAction.READ_PAGES
        assert permission.effect == PermissionEffect.ALLOW
        assert permission.created_at is not None
    
    @pytest.mark.asyncio
    async def test_user_group_assignment(self, test_db: AsyncSession, test_user: User):
        """Test assigning user to permission group."""
        # Create group
        group = PermissionGroup(name="test-group")
        test_db.add(group)
        await test_db.commit()
        
        # Assign user to group
        user_group = UserGroup(user_id=test_user.id, group_id=group.id)
        test_db.add(user_group)
        await test_db.commit()
        
        # Verify assignment
        stmt = select(UserGroup).where(
            UserGroup.user_id == test_user.id,
            UserGroup.group_id == group.id
        )
        result = await test_db.execute(stmt)
        assignment = result.scalar_one_or_none()
        
        assert assignment is not None
        assert assignment.user_id == test_user.id
        assert assignment.group_id == group.id
        assert assignment.assigned_at is not None
    
    @pytest.mark.asyncio
    async def test_query_user_permissions(self, test_db: AsyncSession, test_user: User):
        """Test querying user permissions through groups."""
        from app.models.permission import PermissionAction, PermissionEffect
        
        # Create group and permission
        group = PermissionGroup(name="test-group")
        test_db.add(group)
        await test_db.commit()
        
        permission = Permission(
            group_id=group.id,
            resource_pattern="/docs/*",
            action=PermissionAction.READ_PAGES,
            effect=PermissionEffect.ALLOW
        )
        test_db.add(permission)
        await test_db.commit()
        
        # Assign user to group
        user_group = UserGroup(user_id=test_user.id, group_id=group.id)
        test_db.add(user_group)
        await test_db.commit()
        
        # Query user permissions
        stmt = select(Permission).join(UserGroup).where(UserGroup.user_id == test_user.id)
        result = await test_db.execute(stmt)
        permissions = result.scalars().all()
        
        assert len(permissions) >= 1
        assert any(perm.resource_pattern == "/docs/*" for perm in permissions)


@pytest.mark.integration
class TestComplexDatabaseQueries:
    """Test complex database queries and relationships."""
    
    @pytest.mark.asyncio
    async def test_document_with_tags_and_revisions(self, test_db: AsyncSession, test_user: User):
        """Test querying document with related tags and revisions."""
        # Create document
        document = DocumentFactory.create_document(
            title="Complex Document",
            author_id=test_user.id
        )
        test_db.add(document)
        await test_db.commit()
        
        # Create tags and associate with document
        tag1 = TagFactory.create_tag(name="tag1")
        tag2 = TagFactory.create_tag(name="tag2")
        test_db.add(tag1)
        test_db.add(tag2)
        await test_db.commit()
        
        doc_tag1 = DocumentTag(document_id=document.id, tag_id=tag1.id)
        doc_tag2 = DocumentTag(document_id=document.id, tag_id=tag2.id)
        test_db.add(doc_tag1)
        test_db.add(doc_tag2)
        await test_db.commit()
        
        # Create revisions
        for i in range(2):
            revision = DocumentRevision(
                document_id=document.id,
                revision_number=i + 1,
                title=f"Title v{i + 1}",
                content=f"Content v{i + 1}",
                author_id=test_user.id
            )
            test_db.add(revision)
        
        await test_db.commit()
        
        # Query document with tags and revisions
        from sqlalchemy.orm import selectinload
        
        stmt = select(Document).where(Document.id == document.id).options(
            selectinload(Document.tags),
            selectinload(Document.revisions)
        )
        result = await test_db.execute(stmt)
        doc_with_relations = result.scalar_one()
        
        # Verify relationships are loaded
        assert len(doc_with_relations.tags) == 2
        assert len(doc_with_relations.revisions) == 2
        assert any(tag.name == "tag1" for tag in doc_with_relations.tags)
        assert any(tag.name == "tag2" for tag in doc_with_relations.tags)
    
    @pytest.mark.asyncio
    async def test_search_documents_with_filters(self, test_db: AsyncSession, test_user: User):
        """Test searching documents with multiple filters."""
        # Create documents with different properties
        doc1 = DocumentFactory.create_document(
            title="Python Guide",
            content="Learn Python programming",
            folder_path="/programming/",
            status=DocumentStatus.PUBLISHED,
            author_id=test_user.id
        )
        doc2 = DocumentFactory.create_document(
            title="JavaScript Tutorial",
            content="Learn JavaScript",
            folder_path="/programming/",
            status=DocumentStatus.DRAFT,
            author_id=test_user.id
        )
        doc3 = DocumentFactory.create_document(
            title="Database Design",
            content="Learn database design",
            folder_path="/database/",
            status=DocumentStatus.PUBLISHED,
            author_id=test_user.id
        )
        
        test_db.add(doc1)
        test_db.add(doc2)
        test_db.add(doc3)
        await test_db.commit()
        
        # Search with multiple filters
        stmt = select(Document).where(
            Document.folder_path == "/programming/",
            Document.status == DocumentStatus.PUBLISHED,
            Document.author_id == test_user.id
        )
        result = await test_db.execute(stmt)
        filtered_docs = result.scalars().all()
        
        # Should only return published documents in programming folder
        assert len(filtered_docs) == 1
        assert filtered_docs[0].title == "Python Guide"
        assert filtered_docs[0].folder_path == "/programming/"
        assert filtered_docs[0].status == DocumentStatus.PUBLISHED