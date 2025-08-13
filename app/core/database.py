"""
Database connection management with SQLAlchemy and connection pooling.
"""
import logging
import time
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool, QueuePool
from sqlalchemy import event
from app.core.config import settings
from app.core.logging import get_logger, DatabaseLogHandler

logger = get_logger(__name__)
db_log_handler = DatabaseLogHandler()


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


# Create async engine with appropriate configuration for development/production
if settings.DEBUG:
    # Simple configuration for development
    engine = create_async_engine(
        settings.DATABASE_URL,
        poolclass=NullPool,
        echo=True,  # Log SQL queries in debug mode
    )
else:
    # Production configuration with connection pooling
    engine = create_async_engine(
        settings.DATABASE_URL,
        poolclass=QueuePool,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_pre_ping=True,
        pool_recycle=3600,  # Recycle connections after 1 hour
        pool_timeout=30,    # Timeout for getting connection from pool
        echo=False,
        # Performance optimizations
        connect_args={
            "server_settings": {
                "application_name": "wiki_app",
                "jit": "off",  # Disable JIT for faster connection times
            },
            "command_timeout": 60,
            "prepared_statement_cache_size": 0,  # Disable prepared statement cache for better memory usage
        },
    )

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# Database event listeners for comprehensive logging
@event.listens_for(engine.sync_engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """Log before SQL execution."""
    context._query_start_time = time.time()
    
    # Log slow query warnings for complex operations
    if any(keyword in statement.lower() for keyword in ['join', 'subquery', 'union', 'group by', 'order by']):
        context._is_complex_query = True


@event.listens_for(engine.sync_engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """Log after SQL execution."""
    if hasattr(context, '_query_start_time'):
        duration = time.time() - context._query_start_time
        
        # Extract operation and table info
        operation = statement.strip().split()[0].upper()
        table_name = "unknown"
        
        # Simple table name extraction
        if "FROM" in statement.upper():
            try:
                parts = statement.upper().split("FROM")[1].split()
                if parts:
                    table_name = parts[0].strip().replace('"', '')
            except:
                pass
        elif "INTO" in statement.upper():
            try:
                parts = statement.upper().split("INTO")[1].split()
                if parts:
                    table_name = parts[0].strip().replace('"', '')
            except:
                pass
        elif "UPDATE" in statement.upper():
            try:
                parts = statement.upper().split("UPDATE")[1].split()
                if parts:
                    table_name = parts[0].strip().replace('"', '')
            except:
                pass
        
        # Log query completion
        if settings.LOG_LEVEL.upper() == "DEBUG" or duration > 0.1:  # Log all queries in debug or slow queries
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(db_log_handler.log_query(
                        operation=operation,
                        table=table_name,
                        duration=duration,
                        row_count=cursor.rowcount if hasattr(cursor, 'rowcount') else None
                    ))
            except:
                pass  # Ignore logging errors
        
        # Log slow queries
        if duration > 0.5:  # Queries taking more than 500ms
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(db_log_handler.log_slow_query(
                        operation=operation,
                        table=table_name,
                        duration=duration,
                        query_params={"statement_preview": statement[:200]}
                    ))
            except:
                pass


@event.listens_for(engine.sync_engine, "handle_error")
def handle_error(exception_context):
    """Log database errors."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(db_log_handler.log_error(
                operation="DATABASE_ERROR",
                error=exception_context.original_exception
            ))
    except:
        pass


@event.listens_for(engine.sync_engine, "connect")
def on_connect(dbapi_connection, connection_record):
    """Log database connections."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(db_log_handler.log_connection_event(
                event_type="connection_created"
            ))
    except:
        pass


@event.listens_for(engine.sync_engine, "close")
def on_close(dbapi_connection, connection_record):
    """Log database disconnections."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(db_log_handler.log_connection_event(
                event_type="connection_closed"
            ))
    except:
        pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency to get database session.
    
    Yields:
        AsyncSession: Database session
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database tables and optimizations."""
    try:
        async with engine.begin() as conn:
            # Try to import models, but don't fail if they don't exist yet
            try:
                from app.models import user, document, folder, tag, permission, comment, file, revision, audit
                logger.info("All models imported successfully")
            except ImportError as e:
                logger.warning(f"Some models could not be imported: {e}")
                # Continue anyway - tables will be created when models are available
            
            # Create all tables
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created successfully")
            
            # Enable required extensions
            await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
            await conn.execute("CREATE EXTENSION IF NOT EXISTS btree_gin")
            logger.info("PostgreSQL extensions enabled")
            
            # Create search vector update function and trigger
            await conn.execute("""
                CREATE OR REPLACE FUNCTION update_document_search_vector()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.search_vector := 
                        setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
                        setweight(to_tsvector('english', COALESCE(NEW.content, '')), 'B');
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """)
            
            await conn.execute("""
                DROP TRIGGER IF EXISTS update_document_search_vector_trigger ON documents;
                CREATE TRIGGER update_document_search_vector_trigger
                    BEFORE INSERT OR UPDATE ON documents
                    FOR EACH ROW EXECUTE FUNCTION update_document_search_vector();
            """)
            logger.info("Search vector triggers created")
            
            # Create tag usage count update function and trigger
            await conn.execute("""
                CREATE OR REPLACE FUNCTION update_tag_usage_count()
                RETURNS TRIGGER AS $$
                BEGIN
                    IF TG_OP = 'INSERT' THEN
                        UPDATE tags SET usage_count = usage_count + 1 WHERE id = NEW.tag_id;
                        RETURN NEW;
                    ELSIF TG_OP = 'DELETE' THEN
                        UPDATE tags SET usage_count = usage_count - 1 WHERE id = OLD.tag_id;
                        RETURN OLD;
                    END IF;
                    RETURN NULL;
                END;
                $$ LANGUAGE plpgsql;
            """)
            
            await conn.execute("""
                DROP TRIGGER IF EXISTS update_tag_usage_count_trigger ON document_tags;
                CREATE TRIGGER update_tag_usage_count_trigger
                    AFTER INSERT OR DELETE ON document_tags
                    FOR EACH ROW EXECUTE FUNCTION update_tag_usage_count();
            """)
            logger.info("Tag usage count triggers created")
            
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


async def close_db() -> None:
    """Close database connections."""
    try:
        await engine.dispose()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error closing database connections: {e}")
        raise