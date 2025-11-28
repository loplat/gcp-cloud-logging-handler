"""
Cloud Logging Handler - A Python logging handler for Google Cloud Logging.

This package provides structured logging with request tracing support,
optimized for FastAPI applications running on Google Cloud Platform.
"""

from cloud_logging_handler.error_handler import add_error_handler
from cloud_logging_handler.handler import CloudLoggingHandler, RequestLogs

__version__ = "0.1.0"
__all__ = [
    "CloudLoggingHandler",
    "RequestLogs",
    "add_error_handler",
    "__version__",
]
