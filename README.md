# Cloud Logging Handler

[![PyPI version](https://badge.fury.io/py/cloud-logging-handler.svg)](https://badge.fury.io/py/cloud-logging-handler)
[![Python Versions](https://img.shields.io/pypi/pyversions/cloud-logging-handler.svg)](https://pypi.org/project/cloud-logging-handler/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Python logging handler for **Google Cloud Logging** with request tracing support.

## Features

- **Structured JSON Logging**: Outputs logs in Google Cloud Logging's structured format
- **Request Tracing**: Automatic trace context propagation via `X-Cloud-Trace-Context` header
- **Log Aggregation**: Aggregates all logs within a single request into one log entry
- **Severity Tracking**: Automatically tracks the highest severity level per request
- **Multi-Framework Support**: FastAPI, Flask, Django, aiohttp, Sanic
- **Auto Framework Detection**: Automatically detects framework from app instance
- **Custom JSON Encoder**: Support for high-performance JSON libraries (e.g., `ujson`)
- **Zero Dependencies**: Core handler has no external dependencies

## Installation

```bash
# Using uv (recommended)
uv add cloud-logging-handler

# Using pip
pip install cloud-logging-handler
```

## Quick Start

### FastAPI / Starlette

```python
import logging
from fastapi import FastAPI, Request
from cloud_logging_handler import CloudLoggingHandler, RequestLogs

app = FastAPI()

# Initialize handler with app for auto framework detection
handler = CloudLoggingHandler(
    app=app,
    project="your-gcp-project-id"
)

logger = logging.getLogger()
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    handler.set_request(RequestLogs(request))
    response = await call_next(request)
    handler.flush()
    return response

@app.get("/")
async def root():
    logging.info("Processing request")
    return {"message": "Hello World"}
```

### Flask

```python
import logging
from flask import Flask, g, request
from cloud_logging_handler import CloudLoggingHandler, RequestLogs

app = Flask(__name__)

handler = CloudLoggingHandler(
    app=app,
    project="your-gcp-project-id"
)

logger = logging.getLogger()
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

@app.before_request
def before_request():
    handler.set_request(RequestLogs(request))

@app.after_request
def after_request(response):
    handler.flush()
    return response

@app.route("/")
def hello():
    logging.info("Processing request")
    return {"message": "Hello World"}
```

### Django

```python
# settings.py
LOGGING = {
    'version': 1,
    'handlers': {
        'cloud': {
            'class': 'cloud_logging_handler.CloudLoggingHandler',
            'framework': 'django',
            'project': 'your-gcp-project-id',
        },
    },
    'root': {
        'handlers': ['cloud'],
        'level': 'DEBUG',
    },
}

# middleware.py
from cloud_logging_handler import CloudLoggingHandler, RequestLogs
import logging

class CloudLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.handler = None
        for h in logging.getLogger().handlers:
            if isinstance(h, CloudLoggingHandler):
                self.handler = h
                break

    def __call__(self, request):
        if self.handler:
            self.handler.set_request(RequestLogs(request))
        response = self.get_response(request)
        if self.handler:
            self.handler.flush()
        return response
```

### aiohttp

```python
import logging
from aiohttp import web
from cloud_logging_handler import CloudLoggingHandler, RequestLogs

app = web.Application()

handler = CloudLoggingHandler(
    app=app,
    project="your-gcp-project-id"
)

logger = logging.getLogger()
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

@web.middleware
async def logging_middleware(request, handler_func):
    handler.set_request(RequestLogs(request))
    response = await handler_func(request)
    handler.flush()
    return response

app.middlewares.append(logging_middleware)

async def hello(request):
    logging.info("Processing request")
    return web.json_response({"message": "Hello World"})

app.router.add_get("/", hello)
```

### Sanic

```python
import logging
from sanic import Sanic, json
from cloud_logging_handler import CloudLoggingHandler, RequestLogs

app = Sanic("MyApp")

handler = CloudLoggingHandler(
    app=app,
    project="your-gcp-project-id"
)

logger = logging.getLogger()
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

@app.middleware("request")
async def before_request(request):
    handler.set_request(RequestLogs(request))

@app.middleware("response")
async def after_request(request, response):
    handler.flush()

@app.get("/")
async def hello(request):
    logging.info("Processing request")
    return json({"message": "Hello World"})
```

### Using with ujson

For better JSON serialization performance:

```python
import ujson
from cloud_logging_handler import CloudLoggingHandler

handler = CloudLoggingHandler(
    app=app,
    json_impl=ujson,
    project="your-gcp-project-id"
)
```

## Configuration

### CloudLoggingHandler Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `app` | `object` | Web application instance for auto framework detection |
| `framework` | `str` | Explicit framework name (`starlette`, `flask`, `django`, `aiohttp`, `sanic`) |
| `trace_header_name` | `str` | HTTP header name for trace context (default: `X-Cloud-Trace-Context`) |
| `json_impl` | `module` | Custom JSON encoder module (must have `dumps` method) |
| `project` | `str` | GCP project ID for trace URL construction |

### Framework Detection

The handler automatically detects the framework from the app instance:

| App Module | Detected Framework |
|------------|-------------------|
| `starlette.*`, `fastapi.*` | `starlette` |
| `flask.*` | `flask` |
| `django.*` | `django` |
| `aiohttp.*` | `aiohttp` |
| `sanic.*` | `sanic` |

You can also explicitly specify the framework:

```python
handler = CloudLoggingHandler(
    framework="flask",
    project="your-gcp-project-id"
)
```

## Log Output Format

### With Request Context

When logging within a request context, logs are aggregated and output as structured JSON:

```json
{
  "severity": "INFO",
  "name": "root",
  "process": 12345,
  "url": "https://example.com/api/endpoint",
  "logging.googleapis.com/trace": "projects/your-project/traces/abc123",
  "logging.googleapis.com/spanId": "def456",
  "message": "\n2025-12-01T12:00:00.000000+00:00\tINFO\tProcessing request\n2025-12-01T12:00:00.001000+00:00\tINFO\tRequest completed"
}
```

### Without Request Context

When logging outside a request context, logs are output as plain text:

```
Processing request
```

## How It Works

1. **Handler Initialization**: Framework-specific wrapper is selected based on `app` or `framework` parameter
2. **Request Start**: Middleware creates a `RequestLogs` context
3. **Log Accumulation**: All log calls within the request are accumulated in `message` field
4. **Severity Tracking**: The highest severity level is tracked
5. **Trace Extraction**: Trace context is extracted from request headers using framework-specific methods
6. **Request End**: `flush()` emits all accumulated logs as a single structured entry

This approach provides several benefits:
- Correlate all logs from a single request
- View logs grouped by trace in Cloud Console
- Reduce log volume while maintaining detail
- Optimized header/URL extraction per framework

## Development

### Setup

```bash
# Clone the repository
git clone https://github.com/loplat/gcp-cloud-logging-handler.git
cd cloud-logging-handler

# Install with dev dependencies using uv
uv sync --all-extras

# Run tests
uv run pytest

# Run linting
uv run ruff check .
uv run ruff format .
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Inspired by [Google Cloud Logging documentation](https://cloud.google.com/logging/docs/structured-logging)
