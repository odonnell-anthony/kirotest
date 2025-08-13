"""
Simplified Redis connection management for development.
"""
import logging
import redis.asyncio as redis
from app.core.config import settings

logger = logging.getLogger(__name__)

# Global Redis connection
redis_client = None


async def init_redis() -> None:
    """Initialize Redis connection."""
    global redis_client
    try:
        redis_client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True
        )
        
        # Test connection
        await redis_client.ping()
        logger.info("Redis connection initialized successfully")
        
    except Exception as e:
        logger.warning(f"Redis initialization failed: {e}")
        # Don't raise in development mode to allow the app to start


async def close_redis() -> None:
    """Close Redis connection."""
    global redis_client
    try:
        if redis_client:
            await redis_client.close()
            logger.info("Redis connection closed")
    except Exception as e:
        logger.error(f"Error closing Redis connection: {e}")


async def get_redis():
    """Get Redis client."""
    return redis_client