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
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from types import ModuleType


class JsonEncoder(Protocol):
    """Protocol for JSON encoder compatibility."""

    def dumps(self, obj: Any) -> str: ...


class RequestLogs:
    """Container for request context and accumulated log entries.

    Attributes:
        request: The HTTP request object (typically from FastAPI/Starlette).
        json_payload: Dictionary containing structured log data.
    """

    def __init__(self, request: Any, json_payload: dict[str, Any] | None = None) -> None:
        self.request = request
        self.json_payload = json_payload


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
        trace_header_name: str | None = None,
        json_impl: ModuleType | JsonEncoder | None = None,
        project: str | None = None,
    ) -> None:
        """Initialize the Cloud Logging Handler.

        Args:
            trace_header_name: HTTP header name for trace context.
                Typically "X-Cloud-Trace-Context" for GCP.
            json_impl: Custom JSON encoder module (e.g., ujson).
                Must have a `dumps` method. Defaults to stdlib json.
            project: GCP project ID for trace URL construction.
        """
        super().__init__(stream=sys.stdout)
        self.trace_header_name = trace_header_name
        self.json: ModuleType | JsonEncoder = json_impl if json_impl else json
        self.project = project

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
        self._request_ctx_var.reset(token)

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record as structured JSON.

        If within a request context, logs are accumulated and the highest
        severity level is tracked. Otherwise, logs are emitted immediately.

        Args:
            record: The log record to emit.
        """
        try:
            msg = self.format(record)
            request_log = self.get_request()

            if not request_log:
                # No request context - emit immediately
                json_payload = {
                    "severity": record.levelname,
                    "name": record.name,
                    "pathname": record.filename,
                    "lineno": record.lineno,
                    "process": record.process,
                    "lines": [
                        {
                            "pathname": record.filename,
                            "lineno": record.lineno,
                            "message": msg,
                        }
                    ],
                }
                self.stream.write(self.json.dumps(json_payload) + self.terminator)
                return

            request = request_log.request

            if not request_log.json_payload:
                # First log in this request - initialize payload
                request_log.json_payload = {
                    "severity": record.levelname,
                    "name": record.name,
                    "process": record.process,
                }

                if request:
                    request_log.json_payload["message"] = str(request.url)
                    self._extract_trace_context(request, request_log)

                request_log.json_payload["lines"] = [
                    {
                        "pathname": record.filename,
                        "lineno": record.lineno,
                        "message": msg,
                    }
                ]
            else:
                # Subsequent log - append and update severity if higher
                cur_level = getattr(logging, record.levelname)
                prev_level = getattr(logging, request_log.json_payload["severity"])
                if cur_level > prev_level:
                    request_log.json_payload["severity"] = record.levelname

                request_log.json_payload["lines"].append(
                    {
                        "pathname": record.filename,
                        "lineno": record.lineno,
                        "message": msg,
                    }
                )

            self.set_request(request_log)

        except RecursionError:
            raise
        except Exception:
            self.handleError(record)

    def _extract_trace_context(self, request: Any, request_log: RequestLogs) -> None:
        """Extract trace context from request headers.

        Args:
            request: HTTP request object with headers attribute.
            request_log: RequestLogs to update with trace information.
        """
        if not self.trace_header_name or request_log.json_payload is None:
            return

        header_name_lower = self.trace_header_name.lower()
        headers = {k.lower(): v for k, v in request.headers.items()}

        if header_name_lower not in headers:
            return

        # Parse: "TRACE_ID/SPAN_ID;o=TRACE_TRUE"
        raw_trace = headers[header_name_lower].split("/")
        trace = raw_trace[0]
        span = None

        if len(raw_trace) > 1:
            span = raw_trace[1].split(";")[0]

        if trace and self.project:
            request_log.json_payload["logging.googleapis.com/trace"] = (
                f"projects/{self.project}/traces/{trace}"
            )

        if span:
            request_log.json_payload["logging.googleapis.com/spanId"] = span

    def flush(self) -> None:
        """Flush accumulated logs for the current request.

        This should be called at the end of request processing to emit
        all accumulated log entries as a single structured log entry.
        """
        request_log = self.get_request()
        if request_log and request_log.json_payload:
            self.stream.write(self.json.dumps(request_log.json_payload) + self.terminator)

            request = request_log.request
            if request and hasattr(request.state, "token") and request.state.token is not None:
                self.reset_request(request.state.token)
