"""
Health check endpoints for container orchestration.
"""
import time
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.core.redis import get_redis
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Basic health check endpoint.
    
    Returns:
        Dict: Health status
    """
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "service": "wiki-app"
    }


@router.get("/health/detailed")
async def detailed_health_check(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """
    Detailed health check including database and Redis connectivity.
    
    Args:
        db: Database session
        
    Returns:
        Dict: Detailed health status
        
    Raises:
        HTTPException: If any service is unhealthy
    """
    health_status = {
        "status": "healthy",
        "timestamp": time.time(),
        "service": "wiki-app",
        "checks": {}
    }
    
    # Check database connectivity
    try:
        start_time = time.time()
        result = await db.execute(text("SELECT 1"))
        db_duration = time.time() - start_time
        
        health_status["checks"]["database"] = {
            "status": "healthy",
            "response_time_ms": round(db_duration * 1000, 2)
        }
        
        await logger.ainfo("Database health check passed", duration_ms=round(db_duration * 1000, 2))
        
    except Exception as e:
        health_status["checks"]["database"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["status"] = "unhealthy"
        await logger.aerror("Database health check failed", error=str(e))
    
    # Check Redis connectivity
    try:
        redis = await get_redis()
        start_time = time.time()
        await redis.ping()
        redis_duration = time.time() - start_time
        
        health_status["checks"]["redis"] = {
            "status": "healthy",
            "response_time_ms": round(redis_duration * 1000, 2)
        }
        
        await logger.ainfo("Redis health check passed", duration_ms=round(redis_duration * 1000, 2))
        
    except Exception as e:
        health_status["checks"]["redis"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["status"] = "unhealthy"
        await logger.aerror("Redis health check failed", error=str(e))
    
    # Return appropriate status code
    if health_status["status"] == "unhealthy":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=health_status
        )
    
    return health_status


@router.get("/health/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """
    Readiness check for Kubernetes-style orchestration.
    
    Args:
        db: Database session
        
    Returns:
        Dict: Readiness status
    """
    try:
        # Check if we can perform basic database operations
        await db.execute(text("SELECT 1"))
        
        # Check Redis
        redis = await get_redis()
        await redis.ping()
        
        return {
            "status": "ready",
            "timestamp": time.time()
        }
        
    except Exception as e:
        await logger.aerror("Readiness check failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not_ready",
                "error": str(e),
                "timestamp": time.time()
            }
        )


@router.get("/health/live")
async def liveness_check() -> Dict[str, Any]:
    """
    Liveness check for Kubernetes-style orchestration.
    
    Returns:
        Dict: Liveness status
    """
    return {
        "status": "alive",
        "timestamp": time.time()
    }