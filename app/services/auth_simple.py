"""
Simple authentication service.
"""
import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from passlib.context import CryptContext
from app.models.user_simple import User

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Service for user authentication."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def hash_password(self, password: str) -> str:
        """Hash a password."""
        return pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return pwd_context.verify(plain_password, hashed_password)
    
    async def create_user(self, username: str, email: str, password: str, full_name: str = None, is_admin: bool = False) -> User:
        """Create a new user."""
        # Check if username or email already exists
        existing_user = await self.db.execute(
            select(User).where(
                (User.username == username) | (User.email == email)
            )
        )
        if existing_user.scalar_one_or_none():
            raise ValueError("Username or email already exists")
        
        user = User(
            username=username,
            email=email,
            password_hash=self.hash_password(password),
            full_name=full_name,
            is_admin=is_admin
        )
        
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        
        return user
    
    async def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Authenticate a user by username and password."""
        result = await self.db.execute(
            select(User).where(User.username == username, User.is_active == True)
        )
        user = result.scalar_one_or_none()
        
        if not user or not self.verify_password(password, user.password_hash):
            return None
        
        return user
    
    async def get_user_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        """Get user by ID."""
        result = await self.db.execute(
            select(User).where(User.id == user_id, User.is_active == True)
        )
        return result.scalar_one_or_none()
    
    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        result = await self.db.execute(
            select(User).where(User.username == username, User.is_active == True)
        )
        return result.scalar_one_or_none()
    
    async def create_default_admin(self) -> User:
        """Create default admin user if no users exist."""
        # Check if any users exist
        result = await self.db.execute(select(User))
        if result.scalar_one_or_none():
            return None  # Users already exist
        
        # Create default admin
        admin_user = await self.create_user(
            username="admin",
            email="admin@wiki.local",
            password="admin123",  # Change this in production!
            full_name="Administrator",
            is_admin=True
        )
        
        return admin_user