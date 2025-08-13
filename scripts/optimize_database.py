#!/usr/bin/env python3
"""
Database optimization script for PostgreSQL performance tuning.
"""
import asyncio
import os
import sys

# Add the app directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.database import engine


async def optimize_database():
    """Apply PostgreSQL performance optimizations."""
    print("Applying database optimizations...")
    
    async with engine.begin() as conn:
        # Enable required extensions
        await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS btree_gin")
        print("✓ Enabled PostgreSQL extensions")
        
        # Update PostgreSQL configuration for better performance
        optimizations = [
            # Memory settings
            "SET shared_preload_libraries = 'pg_stat_statements'",
            
            # Query planner settings
            "SET random_page_cost = 1.1",  # For SSD storage
            "SET effective_cache_size = '256MB'",
            "SET work_mem = '4MB'",
            "SET maintenance_work_mem = '64MB'",
            
            # Connection settings
            "SET max_connections = 100",
            
            # Logging settings for performance monitoring
            "SET log_min_duration_statement = 1000",  # Log slow queries (>1s)
            "SET log_checkpoints = on",
            "SET log_connections = on",
            "SET log_disconnections = on",
            "SET log_lock_waits = on",
        ]
        
        for optimization in optimizations:
            try:
                await conn.execute(optimization)
                print(f"✓ Applied: {optimization}")
            except Exception as e:
                print(f"⚠ Could not apply: {optimization} - {e}")
        
        # Update table statistics for better query planning
        await conn.execute("ANALYZE")
        print("✓ Updated table statistics")
        
        # Create function for updating search vectors
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
        print("✓ Created search vector update function")
        
        # Create trigger for automatic search vector updates
        await conn.execute("""
            DROP TRIGGER IF EXISTS update_document_search_vector_trigger ON documents;
            CREATE TRIGGER update_document_search_vector_trigger
                BEFORE INSERT OR UPDATE ON documents
                FOR EACH ROW EXECUTE FUNCTION update_document_search_vector();
        """)
        print("✓ Created search vector update trigger")
        
        # Create function for updating tag usage counts
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
        print("✓ Created tag usage count update function")
        
        # Create trigger for automatic tag usage count updates
        await conn.execute("""
            DROP TRIGGER IF EXISTS update_tag_usage_count_trigger ON document_tags;
            CREATE TRIGGER update_tag_usage_count_trigger
                AFTER INSERT OR DELETE ON document_tags
                FOR EACH ROW EXECUTE FUNCTION update_tag_usage_count();
        """)
        print("✓ Created tag usage count update trigger")
    
    print("Database optimization completed successfully!")


async def main():
    """Main optimization function."""
    try:
        await optimize_database()
    except Exception as e:
        print(f"Optimization failed: {e}")
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())