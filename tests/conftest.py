"""
Pytest configuration and shared fixtures.
"""
import asyncio
import pytest
import uuid
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from httpx import AsyncClient
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import Base, get_db
from app.models.user import User, UserRole
from app.models.document import Document, DocumentStatus
from app.models.folder import Folder
from app.models.tag import Tag
from app.core.auth import get_current_user
from app.core.config import settings


# Test database URL (in-memory SQLite for fast tests)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Clean up
    await engine.dispose()


@pytest.fixture
async def test_db(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session with transaction rollback."""
    async_session = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        # Start a transaction
        transaction = await session.begin()
        
        try:
            yield session
        finally:
            # Rollback transaction to ensure test isolation
            await transaction.rollback()


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock database session for unit tests."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Mock Redis client."""
    return AsyncMock()


@pytest.fixture
async def test_user(test_db: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        id=uuid.uuid4(),
        username="testuser",
        email="test@example.com",
        password_hash="$2b$12$test_hash",
        role=UserRole.NORMAL,
        is_active=True
    )
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    return user


@pytest.fixture
async def test_admin_user(test_db: AsyncSession) -> User:
    """Create a test admin user."""
    user = User(
        id=uuid.uuid4(),
        username="admin",
        email="admin@example.com",
        password_hash="$2b$12$admin_hash",
        role=UserRole.ADMIN,
        is_active=True
    )
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    return user


@pytest.fixture
async def test_folder(test_db: AsyncSession, test_user: User) -> Folder:
    """Create a test folder."""
    folder = Folder(
        id=uuid.uuid4(),
        name="test-folder",
        path="/test-folder/",
        parent_path="/",
        created_by=test_user.id
    )
    test_db.add(folder)
    await test_db.commit()
    await test_db.refresh(folder)
    return folder


@pytest.fixture
async def test_document(test_db: AsyncSession, test_user: User, test_folder: Folder) -> Document:
    """Create a test document."""
    document = Document(
        id=uuid.uuid4(),
        title="Test Document",
        slug="test-document",
        content="# Test Content\n\nThis is a test document.",
        folder_path=test_folder.path,
        status=DocumentStatus.PUBLISHED,
        author_id=test_user.id
    )
    test_db.add(document)
    await test_db.commit()
    await test_db.refresh(document)
    return document


@pytest.fixture
async def test_tag(test_db: AsyncSession) -> Tag:
    """Create a test tag."""
    tag = Tag(
        id=uuid.uuid4(),
        name="python",
        description="Python programming language",
        color="#3776ab",
        usage_count=0
    )
    test_db.add(tag)
    await test_db.commit()
    await test_db.refresh(tag)
    return tag


@pytest.fixture
def mock_current_user(test_user: User):
    """Mock current user dependency."""
    async def _mock_current_user():
        return test_user
    return _mock_current_user


@pytest.fixture
def mock_current_admin_user(test_admin_user: User):
    """Mock current admin user dependency."""
    async def _mock_current_admin_user():
        return test_admin_user
    return _mock_current_admin_user


@pytest.fixture
async def test_client(test_db: AsyncSession, mock_current_user) -> AsyncGenerator[AsyncClient, None]:
    """Create test client with database override."""
    
    async def override_get_db():
        yield test_db
    
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = mock_current_user
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    
    # Clean up overrides
    app.dependency_overrides.clear()


@pytest.fixture
def sync_test_client() -> TestClient:
    """Create synchronous test client for simple tests."""
    return TestClient(app)


# Factory fixtures for creating test data
class UserFactory:
    """Factory for creating test users."""
    
    @staticmethod
    def create_user(
        username: str = None,
        email: str = None,
        role: UserRole = UserRole.NORMAL,
        is_active: bool = True,
        **kwargs
    ) -> User:
        """Create a user instance (not persisted)."""
        user_id = uuid.uuid4()
        return User(
            id=user_id,
            username=username or f"user_{user_id.hex[:8]}",
            email=email or f"test_{user_id.hex[:8]}@example.com",
            password_hash="$2b$12$test_hash",
            role=role,
            is_active=is_active,
            **kwargs
        )
    
    @staticmethod
    async def create_and_save_user(db: AsyncSession, **kwargs) -> User:
        """Create and save a user to the database."""
        user = UserFactory.create_user(**kwargs)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


class DocumentFactory:
    """Factory for creating test documents."""
    
    @staticmethod
    def create_document(
        title: str = None,
        content: str = None,
        author_id: uuid.UUID = None,
        folder_path: str = "/",
        status: DocumentStatus = DocumentStatus.PUBLISHED,
        **kwargs
    ) -> Document:
        """Create a document instance (not persisted)."""
        doc_id = uuid.uuid4()
        return Document(
            id=doc_id,
            title=title or f"Test Document {doc_id.hex[:8]}",
            slug=kwargs.get('slug') or f"test-document-{doc_id.hex[:8]}",
            content=content or "# Test Content\n\nThis is a test document.",
            folder_path=folder_path,
            status=status,
            author_id=author_id or uuid.uuid4(),
            **kwargs
        )
    
    @staticmethod
    async def create_and_save_document(db: AsyncSession, **kwargs) -> Document:
        """Create and save a document to the database."""
        document = DocumentFactory.create_document(**kwargs)
        db.add(document)
        await db.commit()
        await db.refresh(document)
        return document


class TagFactory:
    """Factory for creating test tags."""
    
    @staticmethod
    def create_tag(
        name: str = None,
        description: str = None,
        color: str = "#007acc",
        usage_count: int = 0,
        **kwargs
    ) -> Tag:
        """Create a tag instance (not persisted)."""
        tag_id = uuid.uuid4()
        return Tag(
            id=tag_id,
            name=name or f"tag-{tag_id.hex[:8]}",
            description=description,
            color=color,
            usage_count=usage_count,
            **kwargs
        )
    
    @staticmethod
    async def create_and_save_tag(db: AsyncSession, **kwargs) -> Tag:
        """Create and save a tag to the database."""
        tag = TagFactory.create_tag(**kwargs)
        db.add(tag)
        await db.commit()
        await db.refresh(tag)
        return tag


# Performance testing utilities
@pytest.fixture
def performance_timer():
    """Timer utility for performance tests."""
    import time
    
    class Timer:
        def __init__(self):
            self.start_time = None
            self.end_time = None
        
        def start(self):
            self.start_time = time.perf_counter()
        
        def stop(self):
            self.end_time = time.perf_counter()
        
        @property
        def elapsed_ms(self) -> float:
            if self.start_time is None or self.end_time is None:
                return 0.0
            return (self.end_time - self.start_time) * 1000
    
    return Timer()


# Security testing utilities
@pytest.fixture
def security_test_data():
    """Common security test data."""
    return {
        "xss_payloads": [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>",
            "';alert('xss');//",
        ],
        "sql_injection_payloads": [
            "'; DROP TABLE users; --",
            "' OR '1'='1",
            "1' UNION SELECT * FROM users --",
            "'; INSERT INTO users VALUES ('hacker', 'password'); --",
        ],
        "path_traversal_payloads": [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
        ]
    }