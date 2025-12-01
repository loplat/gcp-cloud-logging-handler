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

### Basic Usage

```python
import logging
from cloud_logging_handler import CloudLoggingHandler

# Create handler
handler = CloudLoggingHandler(
    trace_header_name="X-Cloud-Trace-Context",
    project="your-gcp-project-id"
)

# Configure logging
logger = logging.getLogger()
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

# Log messages
logger.info("Hello, Cloud Logging!")
```

### FastAPI Integration

```python
import logging
import os
from fastapi import FastAPI, Request
from cloud_logging_handler import CloudLoggingHandler, RequestLogs

app = FastAPI()

# Initialize handler
handler = CloudLoggingHandler(
    trace_header_name="X-Cloud-Trace-Context",
    project=os.environ.get("GCP_PROJECT"),
)

# Configure logging
logger = logging.getLogger()
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

# Add middleware for request context
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    request.state.token = handler.set_request(RequestLogs(request, None))
    response = await call_next(request)
    handler.flush()
    return response

@app.get("/")
async def root():
    logging.info("Processing request")
    return {"message": "Hello World"}
```

### Using with ujson

For better JSON serialization performance:

```python
import ujson
from cloud_logging_handler import CloudLoggingHandler

handler = CloudLoggingHandler(
    trace_header_name="X-Cloud-Trace-Context",
    json_impl=ujson,
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

## Configuration

### CloudLoggingHandler Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `trace_header_name` | `str` | HTTP header name for trace context (e.g., `X-Cloud-Trace-Context`) |
| `json_impl` | `module` | Custom JSON encoder module (must have `dumps` method) |
| `project` | `str` | GCP project ID for trace URL construction |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `GCP_PROJECT` | Google Cloud Project ID |

## How It Works

1. **Request Start**: Middleware creates a `RequestLogs` context
2. **Log Accumulation**: All log calls within the request are accumulated in `message` field
3. **Severity Tracking**: The highest severity level is tracked
4. **Trace Extraction**: Trace context is extracted from request headers
5. **Request End**: `flush()` emits all accumulated logs as a single structured entry

This approach provides several benefits:
- Correlate all logs from a single request
- View logs grouped by trace in Cloud Console
- Reduce log volume while maintaining detail

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
