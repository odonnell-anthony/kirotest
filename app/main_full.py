"""
Full-featured FastAPI application with PostgreSQL database.
"""
import asyncio
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database_simple import init_db, close_db, get_db
from app.core.redis_simple import init_redis, close_redis
from app.api.health_simple import router as health_router
from app.api.documents_simple import router as documents_router
from app.services.document_simple import DocumentService
from app.models.document_simple import Document

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Templates
templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Wiki Documentation App with Database")
    
    try:
        # Initialize Redis
        await init_redis()
        logger.info("Redis initialized")
        
        # Initialize database
        await init_db()
        logger.info("Database initialized")
        
        # Import models to ensure tables are created
        from app.models.document_simple import Document
        logger.info("Database models imported")
        
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
        description="Full-featured wiki/documentation application with PostgreSQL",
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
    
    # Web routes
    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request, db: AsyncSession = Depends(get_db)):
        """Home page with wiki interface."""
        service = DocumentService(db)
        doc_count = await service.get_document_count()
        recent_docs = await service.list_documents(limit=5)
        
        return templates.TemplateResponse("home_full.html", {
            "request": request,
            "title": "Wiki Documentation App",
            "doc_count": doc_count,
            "recent_docs": recent_docs
        })
    
    @app.get("/docs", response_class=HTMLResponse)
    async def docs_list(request: Request, db: AsyncSession = Depends(get_db)):
        """List all documents."""
        service = DocumentService(db)
        documents = await service.list_documents(limit=100)
        
        return templates.TemplateResponse("docs_list_full.html", {
            "request": request,
            "title": "All Documents",
            "documents": documents
        })
    
    @app.get("/create", response_class=HTMLResponse)
    async def create_document_page(request: Request):
        """Create new document page."""
        return templates.TemplateResponse("create_doc_full.html", {
            "request": request,
            "title": "Create Document"
        })
    
    @app.post("/create", response_class=HTMLResponse)
    async def create_document_form(
        request: Request,
        title: str = Form(...),
        content: str = Form(...),
        summary: str = Form(None),
        db: AsyncSession = Depends(get_db)
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
            return templates.TemplateResponse("create_doc_full.html", {
                "request": request,
                "title": "Create Document",
                "error": f"Error creating document: {str(e)}",
                "form_data": {"title": title, "content": content, "summary": summary}
            })
    
    @app.get("/doc/{document_id}", response_class=HTMLResponse)
    async def view_document(request: Request, document_id: str, db: AsyncSession = Depends(get_db)):
        """View a specific document."""
        try:
            doc_uuid = uuid.UUID(document_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid document ID")
        
        service = DocumentService(db)
        document = await service.get_document_by_id(doc_uuid)
        
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        return templates.TemplateResponse("view_doc_full.html", {
            "request": request,
            "title": document.title,
            "document": document
        })
    
    @app.get("/doc/{document_id}/edit", response_class=HTMLResponse)
    async def edit_document_page(request: Request, document_id: str, db: AsyncSession = Depends(get_db)):
        """Edit document page."""
        try:
            doc_uuid = uuid.UUID(document_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid document ID")
        
        service = DocumentService(db)
        document = await service.get_document_by_id(doc_uuid)
        
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        return templates.TemplateResponse("edit_doc_full.html", {
            "request": request,
            "title": f"Edit: {document.title}",
            "document": document
        })
    
    @app.post("/doc/{document_id}/edit", response_class=HTMLResponse)
    async def edit_document_form(
        request: Request,
        document_id: str,
        title: str = Form(...),
        content: str = Form(...),
        summary: str = Form(None),
        db: AsyncSession = Depends(get_db)
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
            return templates.TemplateResponse("edit_doc_full.html", {
                "request": request,
                "title": f"Edit: {document.title if document else 'Document'}",
                "document": document,
                "error": f"Error updating document: {str(e)}",
                "form_data": {"title": title, "content": content, "summary": summary}
            })
    
    @app.get("/search", response_class=HTMLResponse)
    async def search_page(request: Request, q: str = "", db: AsyncSession = Depends(get_db)):
        """Search page."""
        results = []
        if q:
            service = DocumentService(db)
            results = await service.search_documents(query=q, limit=50)
        
        return templates.TemplateResponse("search_full.html", {
            "request": request,
            "title": "Search",
            "query": q,
            "results": results
        })
    
    @app.post("/doc/{document_id}/delete")
    async def delete_document_form(document_id: str, db: AsyncSession = Depends(get_db)):
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
    
    return app


app = create_app()