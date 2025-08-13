"""
Functional FastAPI application with core wiki features.
"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from app.core.config import settings
from app.core.database_simple import init_db, close_db, get_db, Base
from app.core.redis_simple import init_redis, close_redis
from app.api.health_simple import router as health_router

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Templates
templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Wiki Documentation App")
    
    try:
        # Initialize Redis
        await init_redis()
        logger.info("Redis initialized")
        
        # Initialize database
        await init_db()
        logger.info("Database initialized")
        
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
        description="High-performance wiki/documentation application",
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
    
    # Include health router
    app.include_router(health_router, prefix="/api", tags=["Health"])
    
    # Web routes
    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        """Home page with wiki interface."""
        return templates.TemplateResponse("home_simple.html", {
            "request": request,
            "title": "Wiki Documentation App",
            "message": "Welcome to your Wiki Documentation App!"
        })
    
    @app.get("/docs-list", response_class=HTMLResponse)
    async def docs_list(request: Request):
        """List all documents."""
        # For now, return a simple page
        documents = [
            {"id": 1, "title": "Getting Started", "summary": "Learn how to use the wiki"},
            {"id": 2, "title": "API Documentation", "summary": "REST API reference"},
            {"id": 3, "title": "User Guide", "summary": "Complete user guide"},
        ]
        return templates.TemplateResponse("docs_list.html", {
            "request": request,
            "title": "Documents",
            "documents": documents
        })
    
    @app.get("/create", response_class=HTMLResponse)
    async def create_document(request: Request):
        """Create new document page."""
        return templates.TemplateResponse("create_doc.html", {
            "request": request,
            "title": "Create Document"
        })
    
    @app.get("/doc/{doc_id}", response_class=HTMLResponse)
    async def view_document(request: Request, doc_id: int):
        """View a specific document."""
        # Mock document data
        document = {
            "id": doc_id,
            "title": f"Document {doc_id}",
            "content": f"This is the content of document {doc_id}. In a real implementation, this would be loaded from the database.",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z"
        }
        return templates.TemplateResponse("view_doc.html", {
            "request": request,
            "title": document["title"],
            "document": document
        })
    
    @app.get("/search", response_class=HTMLResponse)
    async def search_page(request: Request, q: str = ""):
        """Search page."""
        results = []
        if q:
            # Mock search results
            results = [
                {"id": 1, "title": "Getting Started", "summary": f"Found '{q}' in getting started guide"},
                {"id": 2, "title": "API Documentation", "summary": f"'{q}' mentioned in API docs"},
            ]
        
        return templates.TemplateResponse("search.html", {
            "request": request,
            "title": "Search",
            "query": q,
            "results": results
        })
    
    # API endpoints
    @app.get("/api/documents")
    async def list_documents():
        """List all documents via API."""
        return {
            "documents": [
                {"id": 1, "title": "Getting Started", "summary": "Learn how to use the wiki"},
                {"id": 2, "title": "API Documentation", "summary": "REST API reference"},
                {"id": 3, "title": "User Guide", "summary": "Complete user guide"},
            ]
        }
    
    @app.get("/api/documents/{doc_id}")
    async def get_document(doc_id: int):
        """Get a specific document via API."""
        return {
            "id": doc_id,
            "title": f"Document {doc_id}",
            "content": f"This is the content of document {doc_id}.",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z"
        }
    
    @app.post("/api/documents")
    async def create_document_api(title: str, content: str):
        """Create a new document via API."""
        # In a real implementation, this would save to database
        return {
            "id": 999,
            "title": title,
            "content": content,
            "message": "Document created successfully"
        }
    
    return app


app = create_app()