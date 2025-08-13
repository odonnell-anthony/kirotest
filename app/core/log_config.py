"""
Comprehensive logging configuration for production deployment.
"""
import os
import logging.config
from pathlib import Path
from app.core.config import settings

# Ensure log directory exists
LOG_DIR = Path("/app/logs")
LOG_DIR.mkdir(exist_ok=True)

# Comprehensive logging configuration
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s %(correlation_id)s",
            "datefmt": "%Y-%m-%dT%H:%M:%S"
        },
        "detailed": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(correlation_id)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S"
        },
        "simple": {
            "format": "%(levelname)s - %(message)s"
        }
    },
    "filters": {
        "correlation_id": {
            "()": "app.core.logging.CorrelationIdFilter"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "json" if settings.LOG_FORMAT.lower() == "json" else "detailed",
            "stream": "ext://sys.stdout",
            "filters": ["correlation_id"]
        },
        "app_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "INFO",
            "formatter": "json" if settings.LOG_FORMAT.lower() == "json" else "detailed",
            "filename": "/app/logs/app.log",
            "maxBytes": 100 * 1024 * 1024,  # 100MB
            "backupCount": 10,
            "filters": ["correlation_id"]
        },
        "error_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "ERROR",
            "formatter": "json" if settings.LOG_FORMAT.lower() == "json" else "detailed",
            "filename": "/app/logs/error.log",
            "maxBytes": 50 * 1024 * 1024,  # 50MB
            "backupCount": 5,
            "filters": ["correlation_id"]
        },
        "security_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "WARNING",
            "formatter": "json" if settings.LOG_FORMAT.lower() == "json" else "detailed",
            "filename": "/app/logs/security.log",
            "maxBytes": 50 * 1024 * 1024,  # 50MB
            "backupCount": 10,
            "filters": ["correlation_id"]
        },
        "database_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "INFO",
            "formatter": "json" if settings.LOG_FORMAT.lower() == "json" else "detailed",
            "filename": "/app/logs/database.log",
            "maxBytes": 100 * 1024 * 1024,  # 100MB
            "backupCount": 5,
            "filters": ["correlation_id"]
        },
        "performance_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "WARNING",
            "formatter": "json" if settings.LOG_FORMAT.lower() == "json" else "detailed",
            "filename": "/app/logs/performance.log",
            "maxBytes": 50 * 1024 * 1024,  # 50MB
            "backupCount": 5,
            "filters": ["correlation_id"]
        },
        "audit_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "INFO",
            "formatter": "json",  # Always use JSON for audit logs
            "filename": "/app/logs/audit.log",
            "maxBytes": 100 * 1024 * 1024,  # 100MB
            "backupCount": 20,  # Keep more audit logs
            "filters": ["correlation_id"]
        }
    },
    "loggers": {
        # Application loggers
        "app": {
            "level": settings.LOG_LEVEL.upper(),
            "handlers": ["console", "app_file", "error_file"],
            "propagate": False
        },
        "app.security": {
            "level": "INFO",
            "handlers": ["console", "security_file", "error_file"],
            "propagate": False
        },
        "app.database": {
            "level": "INFO",
            "handlers": ["console", "database_file", "error_file"],
            "propagate": False
        },
        "app.performance": {
            "level": "WARNING",
            "handlers": ["console", "performance_file"],
            "propagate": False
        },
        "app.audit": {
            "level": "INFO",
            "handlers": ["audit_file"],
            "propagate": False
        },
        
        # Third-party loggers
        "sqlalchemy.engine": {
            "level": "WARNING",
            "handlers": ["database_file"],
            "propagate": False
        },
        "sqlalchemy.pool": {
            "level": "WARNING",
            "handlers": ["database_file"],
            "propagate": False
        },
        "aioredis": {
            "level": "WARNING",
            "handlers": ["app_file"],
            "propagate": False
        },
        "uvicorn": {
            "level": "INFO",
            "handlers": ["console", "app_file"],
            "propagate": False
        },
        "uvicorn.access": {
            "level": "INFO",
            "handlers": ["app_file"],
            "propagate": False
        },
        "fastapi": {
            "level": "INFO",
            "handlers": ["console", "app_file"],
            "propagate": False
        },
        "celery": {
            "level": "INFO",
            "handlers": ["console", "app_file"],
            "propagate": False
        }
    },
    "root": {
        "level": "WARNING",
        "handlers": ["console", "error_file"]
    }
}


class CorrelationIdFilter(logging.Filter):
    """Filter to add correlation ID to log records."""
    
    def filter(self, record):
        """Add correlation ID to log record."""
        from app.core.logging import get_correlation_id
        
        correlation_id = get_correlation_id()
        record.correlation_id = correlation_id or "no-correlation-id"
        return True


def setup_production_logging():
    """Setup production logging configuration."""
    logging.config.dictConfig(LOGGING_CONFIG)
    
    # Create a test log entry
    logger = logging.getLogger("app")
    logger.info("Production logging configuration loaded successfully")


def get_log_files():
    """Get list of current log files with sizes."""
    log_files = []
    
    for log_file in LOG_DIR.glob("*.log*"):
        try:
            size = log_file.stat().st_size
            log_files.append({
                "name": log_file.name,
                "path": str(log_file),
                "size_bytes": size,
                "size_mb": round(size / (1024 * 1024), 2)
            })
        except OSError:
            continue
    
    return sorted(log_files, key=lambda x: x["name"])


def cleanup_old_logs(days_to_keep: int = 30):
    """Clean up log files older than specified days."""
    import time
    
    cutoff_time = time.time() - (days_to_keep * 24 * 60 * 60)
    cleaned_files = []
    
    for log_file in LOG_DIR.glob("*.log.*"):
        try:
            if log_file.stat().st_mtime < cutoff_time:
                log_file.unlink()
                cleaned_files.append(str(log_file))
        except OSError:
            continue
    
    return cleaned_files


def get_log_stats():
    """Get logging statistics."""
    log_files = get_log_files()
    
    total_size = sum(f["size_bytes"] for f in log_files)
    
    return {
        "total_files": len(log_files),
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "files": log_files
    }