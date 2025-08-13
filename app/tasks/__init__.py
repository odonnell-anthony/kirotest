"""
Background tasks for the Wiki Documentation App.
"""
from .cleanup import cleanup_old_logs

__all__ = ["cleanup_old_logs"]