"""
Full-featured FastAPI application with authentication and PostgreSQL database.
"""
import asyncio
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException, Form, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError, jwt
from datetime import datetime, timedelta

from app.core.config import settings
from app.core.database_simple import init_db, close_db, get_db
from app.core.redis_simple import init_redis, close_redis
from app.api.health_simple import router as health_router
from app.api.documents_simple import router as documents_router
from app.services.document_simple import DocumentService
from app.services.auth_simple import AuthService
from app.models.document_simple import Document
from app.models.user_simple import User

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Templates
templates = Jinja2Templates(directory="app/templates")

# Security
security = HTTPBearer(auto_error=False)

# JWT settings
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


def create_access_token(data: dict, expires_delta: timedelta = None):
    """Create JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """Get current authenticated user."""
    # Try to get token from Authorization header
    token = None
    if credentials:
        token = credentials.credentials
    
    # If no header token, try to get from cookie
    if not token:
        token = request.cookies.get("access_token")
    
    if not token:
        return None
    
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
    except JWTError:
        return None
    
    auth_service = AuthService(db)
    user = await auth_service.get_user_by_id(uuid.UUID(user_id))
    return user


async def require_auth(current_user: User = Depends(get_current_user)):
    """Require authentication."""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return current_user


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Wiki Documentation App with Authentication")
    
    try:
        # Initialize Redis
        await init_redis()
        logger.info("Redis initialized")
        
        # Initialize database
        await init_db()
        logger.info("Database initialized")
        
        # Import models to ensure tables are created
        from app.models.document_simple import Document
        from app.models.user_simple import User
        logger.info("Database models imported")
        
        # Create default admin user
        async with AsyncSession(bind=init_db.__globals__['engine']) as db:
            auth_service = AuthService(db)
            admin_user = await auth_service.create_default_admin()
            if admin_user:
                logger.info("Default admin user created: admin/admin123")
            else:
                logger.info("Users already exist, skipping default admin creation")
        
        logger.info("Application startup completed")
        
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        # Don't raise to allow app to start anyway
    
    yield
    
    # Shutdown
    logger.info("Shutting down Wiki Documentation App")
    
    try:
        await close_db()
        await close_redis()
        logger.info("Application shutdown completed")
        
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="Wiki Documentation App",
        description="Full-featured wiki/documentation application with authentication",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        lifespan=lifespan,
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Mount static files
    try:
        app.mount("/static", StaticFiles(directory="static"), name="static")
    except Exception as e:
        logger.warning(f"Could not mount static files: {e}")
    
    # Include API routers
    app.include_router(health_router, prefix="/api", tags=["Health"])
    app.include_router(documents_router, prefix="/api", tags=["Documents"])
    
    # Authentication routes
    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        """Login page."""
        return templates.TemplateResponse("login.html", {
            "request": request,
            "title": "Login"
        })
    
    @app.post("/login")
    async def login_form(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        db: AsyncSession = Depends(get_db)
    ):
        """Handle login form submission."""
        auth_service = AuthService(db)
        user = await auth_service.authenticate_user(username, password)
        
        if not user:
            return templates.TemplateResponse("login.html", {
                "request": request,
                "title": "Login",
                "error": "Invalid username or password",
                "form_data": {"username": username}
            })
        
        # Create access token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": str(user.id)}, expires_delta=access_token_expires
        )
        
        # Redirect to home page with token in cookie
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(
            key="access_token",
            value=access_token,
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            httponly=True
        )
        return response
    
    @app.get("/logout")
    async def logout():
        """Logout user."""
        response = RedirectResponse(url="/login", status_code=302)
        response.delete_cookie(key="access_token")
        return response
    
    # Protected web routes
    @app.get("/", response_class=HTMLResponse)
    async def home(
        request: Request, 
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Home page with wiki interface."""
        if not current_user:
            return RedirectResponse(url="/login", status_code=302)
        
        service = DocumentService(db)
        doc_count = await service.get_document_count()
        recent_docs = await service.list_documents(limit=5)
        
        return templates.TemplateResponse("home_auth.html", {
            "request": request,
            "title": "Wiki Documentation App",
            "doc_count": doc_count,
            "recent_docs": recent_docs,
            "current_user": current_user
        })
    
    @app.get("/docs", response_class=HTMLResponse)
    async def docs_list(
        request: Request, 
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_auth)
    ):
        """List all documents."""
        service = DocumentService(db)
        documents = await service.list_documents(limit=100)
        
        return templates.TemplateResponse("docs_list_auth.html", {
            "request": request,
            "title": "All Documents",
            "documents": documents,
            "current_user": current_user
        })
    
    @app.get("/create", response_class=HTMLResponse)
    async def create_document_page(
        request: Request,
        current_user: User = Depends(require_auth)
    ):
        """Create new document page."""
        return templates.TemplateResponse("create_doc_auth.html", {
            "request": request,
            "title": "Create Document",
            "current_user": current_user
        })
    
    @app.post("/create", response_class=HTMLResponse)
    async def create_document_form(
        request: Request,
        title: str = Form(...),
        content: str = Form(...),
        summary: str = Form(None),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_auth)
    ):
        """Handle document creation form submission."""
        service = DocumentService(db)
        
        try:
            document = await service.create_document(
                title=title,
                content=content,
                summary=summary
            )
            return RedirectResponse(url=f"/doc/{document.id}", status_code=302)
        
        except Exception as e:
            return templates.TemplateResponse("create_doc_auth.html", {
                "request": request,
                "title": "Create Document",
                "current_user": current_user,
                "error": f"Error creating document: {str(e)}",
                "form_data": {"title": title, "content": content, "summary": summary}
            })
    
    @app.get("/doc/{document_id}", response_class=HTMLResponse)
    async def view_document(
        request: Request, 
        document_id: str, 
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_auth)
    ):
        """View a specific document."""
        try:
            doc_uuid = uuid.UUID(document_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid document ID")
        
        service = DocumentService(db)
        document = await service.get_document_by_id(doc_uuid)
        
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        return templates.TemplateResponse("view_doc_auth.html", {
            "request": request,
            "title": document.title,
            "document": document,
            "current_user": current_user
        })
    
    @app.get("/doc/{document_id}/edit", response_class=HTMLResponse)
    async def edit_document_page(
        request: Request, 
        document_id: str, 
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_auth)
    ):
        """Edit document page."""
        try:
            doc_uuid = uuid.UUID(document_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid document ID")
        
        service = DocumentService(db)
        document = await service.get_document_by_id(doc_uuid)
        
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        return templates.TemplateResponse("edit_doc_auth.html", {
            "request": request,
            "title": f"Edit: {document.title}",
            "document": document,
            "current_user": current_user
        })
    
    @app.post("/doc/{document_id}/edit", response_class=HTMLResponse)
    async def edit_document_form(
        request: Request,
        document_id: str,
        title: str = Form(...),
        content: str = Form(...),
        summary: str = Form(None),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_auth)
    ):
        """Handle document edit form submission."""
        try:
            doc_uuid = uuid.UUID(document_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid document ID")
        
        service = DocumentService(db)
        
        try:
            document = await service.update_document(
                document_id=doc_uuid,
                title=title,
                content=content,
                summary=summary
            )
            
            if not document:
                raise HTTPException(status_code=404, detail="Document not found")
            
            return RedirectResponse(url=f"/doc/{document.id}", status_code=302)
        
        except Exception as e:
            document = await service.get_document_by_id(doc_uuid)
            return templates.TemplateResponse("edit_doc_auth.html", {
                "request": request,
                "title": f"Edit: {document.title if document else 'Document'}",
                "document": document,
                "current_user": current_user,
                "error": f"Error updating document: {str(e)}",
                "form_data": {"title": title, "content": content, "summary": summary}
            })
    
    @app.get("/search", response_class=HTMLResponse)
    async def search_page(
        request: Request, 
        q: str = "", 
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_auth)
    ):
        """Search page."""
        results = []
        if q:
            service = DocumentService(db)
            results = await service.search_documents(query=q, limit=50)
        
        return templates.TemplateResponse("search_auth.html", {
            "request": request,
            "title": "Search",
            "query": q,
            "results": results,
            "current_user": current_user
        })
    
    @app.post("/doc/{document_id}/delete")
    async def delete_document_form(
        document_id: str, 
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(require_auth)
    ):
        """Handle document deletion."""
        try:
            doc_uuid = uuid.UUID(document_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid document ID")
        
        service = DocumentService(db)
        success = await service.delete_document(doc_uuid)
        
        if not success:
            raise HTTPException(status_code=404, detail="Document not found")
        
        return RedirectResponse(url="/docs", status_code=302)
    
    # Public route for unauthenticated users
    @app.get("/public", response_class=HTMLResponse)
    async def public_page(request: Request):
        """Public information page."""
        return templates.TemplateResponse("public.html", {
            "request": request,
            "title": "Wiki Documentation App"
        })
    
    return app


app = create_app()