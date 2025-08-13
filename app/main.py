"""
Main FastAPI application entry point.
"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.database import init_db, close_db
from app.core.redis import init_redis, close_redis
from app.core.logging import setup_logging, set_correlation_id, get_logger
from app.core.security import SecurityMiddleware
from app.core.rate_limit import RateLimitMiddleware
from app.core.middleware import LoggingMiddleware, SecurityLoggingMiddleware
from app.api.health import router as health_router
from app.api.auth import router as auth_router
from app.api.permissions import router as permissions_router
from app.api.files import router as files_router
from app.api.documents import router as documents_router
from app.api.folders import router as folders_router
from app.api.comments import router as comments_router
from app.api.timeline import router as timeline_router
from app.api.admin import router as admin_router
from app.api.webhooks import router as webhooks_router
from app.api.search import router as search_router
from app.api.tags import router as tags_router
from app.api.developer import router as developer_router
from app.api.templates import router as templates_router
from app.api.web import router as web_router

# Setup logging
setup_logging()
logger = get_logger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    await logger.ainfo("Starting Wiki Documentation App")
    
    try:
        # Initialize Redis
        await init_redis()
        await logger.ainfo("Redis initialized successfully")
        
        # Initialize database
        await init_db()
        await logger.ainfo("Database initialized successfully")
        
        await logger.ainfo("Application startup completed")
        
    except Exception as e:
        await logger.aerror("Failed to start application", error=str(e))
        raise
    
    yield
    
    # Shutdown
    await logger.ainfo("Shutting down Wiki Documentation App")
    
    try:
        await close_db()
        await close_redis()
        await logger.ainfo("Application shutdown completed")
        
    except Exception as e:
        await logger.aerror("Error during shutdown", error=str(e))


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="Wiki Documentation App",
        description="High-performance wiki/documentation application",
        version="1.0.0",
        docs_url="/api/docs" if settings.DEBUG else None,
        redoc_url="/api/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
    )
    
    # Add logging middleware (first for comprehensive logging)
    app.add_middleware(LoggingMiddleware)
    
    # Add security logging middleware
    app.add_middleware(SecurityLoggingMiddleware)
    
    # Add security middleware
    app.add_middleware(SecurityMiddleware)
    
    # Add rate limiting middleware
    app.add_middleware(RateLimitMiddleware)
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.DEBUG else ["https://yourdomain.com", "http://localhost:8000", "http://127.0.0.1:8000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add rate limiting (legacy slowapi support)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    
    # Middleware for correlation ID
    @app.middleware("http")
    async def correlation_id_middleware(request: Request, call_next):
        """Add correlation ID to each request."""
        correlation_id = request.headers.get("X-Correlation-ID")
        corr_id = set_correlation_id(correlation_id)
        
        # Add correlation ID to response headers
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = corr_id
        
        return response
    
    # Mount static files
    app.mount("/static", StaticFiles(directory="static"), name="static")
    
    # Include API routers
    app.include_router(health_router, prefix="/api", tags=["Health"])
    app.include_router(auth_router, prefix="/api", tags=["Authentication"])
    app.include_router(permissions_router, prefix="/api", tags=["Permissions"])
    app.include_router(files_router, prefix="/api", tags=["Files"])
    app.include_router(documents_router, prefix="/api", tags=["Documents"])
    app.include_router(folders_router, prefix="/api", tags=["Folders"])
    app.include_router(comments_router, prefix="/api", tags=["Comments"])
    app.include_router(timeline_router, prefix="/api", tags=["Timeline"])
    app.include_router(admin_router, prefix="/api", tags=["Admin"])
    app.include_router(webhooks_router, prefix="/api", tags=["Webhooks"])
    app.include_router(search_router, prefix="/api", tags=["Search"])
    app.include_router(tags_router, prefix="/api", tags=["Tags"])
    app.include_router(developer_router, prefix="/api", tags=["Developer"])
    app.include_router(templates_router, prefix="/api", tags=["Templates"])
    
    # Include web routes (no prefix for HTML pages)
    app.include_router(web_router)
    
    return app


app = create_app()