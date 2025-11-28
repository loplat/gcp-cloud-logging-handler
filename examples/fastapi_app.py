"""
Example FastAPI application with Cloud Logging Handler.

This example demonstrates how to integrate the CloudLoggingHandler
with a FastAPI application for structured logging with request tracing.

Usage:
    export GCP_PROJECT="your-gcp-project-id"
    uv run python examples/fastapi_app.py
"""

import logging
import os

import uvicorn
from fastapi import FastAPI, Request
from starlette import status

from cloud_logging_handler import CloudLoggingHandler, RequestLogs, add_error_handler

# Create FastAPI app
app = FastAPI(
    title="Cloud Logging Handler Example",
    description="Example app demonstrating Cloud Logging integration",
)

# Initialize the logging handler
# For better performance, you can use ujson:
#   import ujson
#   json_impl=ujson
cloud_handler = CloudLoggingHandler(
    trace_header_name="X-Cloud-Trace-Context",
    project=os.environ.get("GCP_PROJECT", "demo-project"),
)

# Configure the root logger
logger = logging.getLogger()
logger.addHandler(cloud_handler)
logger.setLevel(logging.DEBUG)
logger.propagate = False

# Add error handlers for proper exception logging
add_error_handler(app, logging_handler=cloud_handler)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """
    Middleware to set up request context for logging.

    This middleware should be declared last to ensure it wraps all other
    middleware and captures the complete request lifecycle.
    """
    # Set the request context for log aggregation
    request.state.token = cloud_handler.set_request(RequestLogs(request, {}))

    # Process the request
    response = await call_next(request)

    # Flush logs at the end of the request
    cloud_handler.flush()

    return response


@app.get("/", status_code=status.HTTP_200_OK)
async def root(request: Request):
    """
    Example endpoint that demonstrates various log levels.
    """
    request_id = id(request)

    logging.debug(f"Debug message for request {request_id}")
    logging.info(f"Info message for request {request_id}")
    logging.warning(f"Warning message for request {request_id}")

    return {"message": "Hello, Cloud Logging!", "request_id": request_id}


@app.get("/error", status_code=status.HTTP_200_OK)
async def trigger_error(request: Request):
    """
    Example endpoint that triggers an error for error handling demonstration.
    """
    logging.debug("About to trigger an error...")

    # This will raise a ZeroDivisionError
    result = 1 / 0

    return {"result": result}


@app.get("/health")
async def health_check():
    """
    Health check endpoint (no logging context needed).
    """
    return {"status": "healthy"}


if __name__ == "__main__":
    print("Starting example server...")
    print("Try these endpoints:")
    print("  - http://localhost:8080/       (normal request with logging)")
    print("  - http://localhost:8080/error  (error handling demonstration)")
    print("  - http://localhost:8080/health (health check)")
    print()

    uvicorn.run(app, host="0.0.0.0", port=8080)
