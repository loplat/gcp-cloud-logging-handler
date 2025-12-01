"""
Google Cloud Logging Handler with request tracing support.

This module provides a custom logging handler that outputs structured JSON logs
compatible with Google Cloud Logging, including trace context propagation.

Reference:
    https://cloud.google.com/logging/docs/structured-logging
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from types import ModuleType


class JsonEncoder(Protocol):
    """Protocol for JSON encoder compatibility."""

    def dumps(self, obj: Any) -> str: ...


class RequestLogs:
    """Container for request context and accumulated log entries.

    Attributes:
        request: The HTTP request object (framework-agnostic).
        json_payload: Dictionary containing structured log data.
    """

    def __init__(self, request: Any, json_payload: dict[str, Any] | None = None) -> None:
        self.request = request
        self.json_payload = json_payload


def _get_framework_from_app(app: Any) -> str:
    """Detect the web framework from app object's module.

    Args:
        app: Web framework application object.

    Returns:
        Framework identifier: 'django', 'flask', 'starlette', 'aiohttp', 'sanic', or 'unknown'.
    """
    if app is None:
        return "unknown"

    module = type(app).__module__

    if module.startswith("django"):
        return "django"
    if module.startswith("flask"):
        return "flask"
    if module.startswith("starlette") or module.startswith("fastapi"):
        return "starlette"
    if module.startswith("aiohttp"):
        return "aiohttp"
    if module.startswith("sanic"):
        return "sanic"

    return "unknown"


class CloudLoggingHandler(logging.StreamHandler):
    """A logging handler for Google Cloud Logging with request tracing.

    This handler outputs structured JSON logs to stdout, which are automatically
    ingested by Google Cloud Logging when running on GCP infrastructure.

    Features:
        - Structured JSON log output
        - Request trace context propagation (X-Cloud-Trace-Context)
        - Log aggregation per request using context variables
        - Severity level tracking (highest severity wins)
        - Custom JSON encoder support (e.g., ujson for performance)
        - Framework-agnostic: works with FastAPI, Flask, Sanic, Django, aiohttp

    Example:
        >>> import logging
        >>> from cloud_logging_handler import CloudLoggingHandler
        >>>
        >>> handler = CloudLoggingHandler(
        ...     trace_header_name="X-Cloud-Trace-Context",
        ...     project="my-gcp-project"
        ... )
        >>> logger = logging.getLogger()
        >>> logger.addHandler(handler)
        >>> logger.setLevel(logging.DEBUG)
    """

    REQUEST_ID_CTX_KEY = "request_id"

    _request_ctx_var: ContextVar[RequestLogs | None] = ContextVar(REQUEST_ID_CTX_KEY, default=None)

    def __init__(
        self,
        app: Any = None,
        trace_header_name: str | None = None,
        json_impl: ModuleType | JsonEncoder | None = None,
        project: str | None = None,
        framework: str | None = None,
    ) -> None:
        """Initialize the Cloud Logging Handler.

        Args:
            app: Web framework application object (FastAPI, Flask, Django, etc.).
                Used to detect framework type once at initialization.
            trace_header_name: HTTP header name for trace context.
                Typically "X-Cloud-Trace-Context" for GCP.
            json_impl: Custom JSON encoder module (e.g., ujson).
                Must have a `dumps` method. Defaults to stdlib json.
            project: GCP project ID for trace URL construction.
            framework: Explicit framework name. If provided, skips auto-detection.
                Valid values: 'django', 'flask', 'starlette', 'aiohttp', 'sanic'.
        """
        super().__init__(stream=sys.stdout)
        self.framework = framework if framework else _get_framework_from_app(app)
        self.trace_header_name = trace_header_name
        self.json: ModuleType | JsonEncoder = json_impl if json_impl else json
        self.project = project

    def _get_header(self, request: Any, header_name: str) -> str | None:
        """Get a header value from request object using cached framework."""
        if request is None:
            return None

        if self.framework == "django":
            meta_key = f"HTTP_{header_name.upper().replace('-', '_')}"
            return request.META.get(meta_key)

        headers = getattr(request, "headers", None)
        if headers is None:
            return None

        if hasattr(headers, "get"):
            value = headers.get(header_name) or headers.get(header_name.lower())
            if value:
                return value

        if hasattr(headers, "items"):
            header_lower = header_name.lower()
            for key, value in headers.items():
                if key.lower() == header_lower:
                    return value

        return None

    def _get_url(self, request: Any) -> str | None:
        """Get URL from request object using cached framework."""
        if request is None:
            return None

        if self.framework == "django":
            return request.build_absolute_uri()

        if self.framework == "flask":
            return str(request.base_url) + request.full_path.rstrip("?")

        if self.framework == "aiohttp":
            if hasattr(request, "url"):
                return str(request.url)
            return request.path

        if hasattr(request, "url"):
            return str(request.url)

        if hasattr(request, "path"):
            return request.path

        return None

    def get_request(self) -> RequestLogs | None:
        """Get the current request context.

        Returns:
            RequestLogs object for current request, or None if not in request context.
        """
        return self._request_ctx_var.get()

    def set_request(self, request: RequestLogs) -> Any:
        """Set the request context for the current async context.

        Args:
            request: RequestLogs object to associate with current context.

        Returns:
            Token that can be used to reset the context.
        """
        return self._request_ctx_var.set(request)

    def reset_request(self, token: Any) -> None:
        """Reset the request context using a token.

        Args:
            token: Token returned from set_request().
        """
        try:
            self._request_ctx_var.reset(token)
        except Exception as e:
            logging.exception(e)

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record as structured JSON.

        If within a request context, logs are accumulated and the highest
        severity level is tracked. Otherwise, logs are emitted as plain text.

        Args:
            record: The log record to emit.
        """
        try:
            msg = self.format(record)
            request_log = self.get_request()

            if not request_log:
                # No request context - emit plain text immediately
                self.stream.write(msg + self.terminator)
                return

            request = request_log.request

            if not request_log.json_payload:
                # First log in this request - initialize payload
                request_log.json_payload = {
                    "severity": record.levelname,
                    "name": record.name,
                    "process": record.process,
                }

                trace = None
                span = None

                if request:
                    url = self._get_url(request)
                    if url:
                        request_log.json_payload["url"] = url

                    if self.trace_header_name:
                        trace_header_value = self._get_header(request, self.trace_header_name)
                        if trace_header_value:
                            # trace can be formatted as "TRACE_ID/SPAN_ID;o=TRACE_TRUE"
                            raw_trace = trace_header_value.split("/")
                            trace = raw_trace[0]
                            if len(raw_trace) > 1:
                                span = raw_trace[1].split(";")[0]

                        if trace and self.project:
                            request_log.json_payload["logging.googleapis.com/trace"] = (
                                f"projects/{self.project}/traces/{trace}"
                            )
                        if span:
                            request_log.json_payload["logging.googleapis.com/spanId"] = span

                request_log.json_payload["severity"] = record.levelname
                request_log.json_payload["message"] = (
                    f"\n{datetime.now(timezone.utc).isoformat()}\t{record.levelname}\t{msg}"
                )
            else:
                # Subsequent log - append and update severity if higher
                cur_level = getattr(logging, record.levelname)
                prev_level = getattr(logging, request_log.json_payload["severity"])
                if cur_level > prev_level:
                    request_log.json_payload["severity"] = record.levelname

                request_log.json_payload["message"] += (
                    f"\n{datetime.now(timezone.utc).isoformat()}\t{record.levelname}\t{msg}"
                )

            self.set_request(request_log)

        except RecursionError:
            raise
        except Exception:
            self.handleError(record)

    def flush(self) -> None:
        """Flush accumulated logs for the current request.

        This should be called at the end of request processing to emit
        all accumulated log entries as a single structured log entry.
        """
        request_log = self.get_request()
        if request_log:
            log = request_log.json_payload
            if not log:
                return

            self.stream.write(self.json.dumps(log) + self.terminator)

            request = request_log.request
            if hasattr(request, "ctx"):
                self.reset_request(request.ctx)
