"""
Cloud Logging Handler - A Python logging handler for Google Cloud Logging.

This package provides structured logging with request tracing support,
optimized for FastAPI applications running on Google Cloud Platform.
"""

from cloud_logging_handler.handler import CloudLoggingHandler, RequestLogs

__version__ = "0.2.5"
__all__ = [
    "CloudLoggingHandler",
    "RequestLogs",
    "__version__",
]
