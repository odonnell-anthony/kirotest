"""
Cleanup tasks for maintenance.
"""
import os
import logging
from datetime import datetime, timedelta
from app.core.celery import celery_app

logger = logging.getLogger(__name__)


@celery_app.task
def cleanup_old_logs():
    """Clean up old log files."""
    try:
        log_dir = "/app/logs"
        if not os.path.exists(log_dir):
            return "Log directory does not exist"
        
        cutoff_date = datetime.now() - timedelta(days=7)
        cleaned_files = 0
        
        for filename in os.listdir(log_dir):
            if filename.endswith('.log.old') or filename.endswith('.log.1'):
                filepath = os.path.join(log_dir, filename)
                file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                
                if file_mtime < cutoff_date:
                    os.remove(filepath)
                    cleaned_files += 1
        
        logger.info(f"Cleaned up {cleaned_files} old log files")
        return f"Cleaned up {cleaned_files} old log files"
        
    except Exception as e:
        logger.error(f"Error cleaning up logs: {e}")
        return f"Error: {e}"