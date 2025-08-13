"""
Simplified FastAPI application for development testing.
"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database_simple import init_db, close_db
from app.core.redis_simple import init_redis, close_redis
from app.api.health_simple import router as health_router

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
    
    # Root endpoint
    @app.get("/")
    async def root():
        return {
            "message": "Wiki Documentation App",
            "status": "running",
            "docs": "/api/docs"
        }
    
    return app


app = create_app()