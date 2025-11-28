"""
FastAPI error handler integration for Cloud Logging.

This module provides exception handlers that integrate with CloudLoggingHandler
to ensure proper log flushing on errors.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI, Request
    from starlette.responses import JSONResponse

    from cloud_logging_handler.handler import CloudLoggingHandler


def add_error_handler(
    app: FastAPI,
    logging_handler: CloudLoggingHandler | None = None,
) -> None:
    """Add exception handlers to a FastAPI application.

    This function registers exception handlers that:
    - Log exceptions with appropriate severity levels
    - Flush the logging handler to ensure logs are emitted
    - Return consistent JSON error responses

    Args:
        app: FastAPI application instance.
        logging_handler: Optional CloudLoggingHandler to flush on errors.

    Example:
        >>> from fastapi import FastAPI
        >>> from cloud_logging_handler import CloudLoggingHandler, add_error_handler
        >>>
        >>> app = FastAPI()
        >>> handler = CloudLoggingHandler(project="my-project")
        >>> add_error_handler(app, logging_handler=handler)
    """
    # Import here to make fastapi optional
    from fastapi import HTTPException
    from starlette.responses import JSONResponse

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        """Handle HTTP exceptions with appropriate logging."""
        msg = {"error": exc.__class__.__name__, "detail": exc.detail}

        if exc.status_code >= 500:
            logging.exception(exc)
        elif exc.status_code >= 400:
            if hasattr(request.state, "log_messages"):
                logging.debug(request.state.log_messages)
            logging.warning(msg)

        if logging_handler:
            logging_handler.flush()

        return JSONResponse(msg, status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle uncaught exceptions with error logging."""
        if hasattr(request.state, "log_messages"):
            logging.debug(request.state.log_messages)
        logging.exception(exc)

        if logging_handler:
            logging_handler.flush()

        return JSONResponse(
            {"error": exc.__class__.__name__, "detail": str(exc)},
            status_code=500,
        )
