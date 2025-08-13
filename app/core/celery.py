"""
Celery configuration for background tasks.
"""
from celery import Celery
from app.core.config import settings

# Create Celery instance
celery_app = Celery(
    "wiki-app",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks"]
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

# Optional: Add periodic tasks
celery_app.conf.beat_schedule = {
    'cleanup-old-logs': {
        'task': 'app.tasks.cleanup_old_logs',
        'schedule': 3600.0,  # Run every hour
    },
}