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
from abc import ABC, abstractmethod
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
        token: ContextVar token for resetting the request context.
    """

    def __init__(self, request: Any) -> None:
        self.request = request
        self.json_payload: dict[str, Any] | None = None
        self.token: Any = None


# ============================================================================
# Request Wrapper Classes (Strategy Pattern)
# ============================================================================


class RequestWrapper(ABC):
    """Abstract base class for framework-specific request wrappers."""

    @abstractmethod
    def get_url(self, request: Any) -> str | None:
        """Extract URL from request object."""
        ...

    @abstractmethod
    def get_header(self, request: Any, header_name: str) -> str | None:
        """Extract header value from request object."""
        ...


class StarletteRequestWrapper(RequestWrapper):
    """Request wrapper for FastAPI/Starlette."""

    def get_url(self, request: Any) -> str | None:
        if request is None:
            return None
        if hasattr(request, "url"):
            return str(request.url)
        return None

    def get_header(self, request: Any, header_name: str) -> str | None:
        if request is None:
            return None
        headers = getattr(request, "headers", None)
        if headers is None:
            return None
        return self._get_header_from_dict(headers, header_name)

    def _get_header_from_dict(self, headers: Any, header_name: str) -> str | None:
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


class FlaskRequestWrapper(RequestWrapper):
    """Request wrapper for Flask."""

    def get_url(self, request: Any) -> str | None:
        if request is None:
            return None
        if hasattr(request, "base_url") and hasattr(request, "full_path"):
            return str(request.base_url) + request.full_path.rstrip("?")
        return None

    def get_header(self, request: Any, header_name: str) -> str | None:
        if request is None:
            return None
        headers = getattr(request, "headers", None)
        if headers is None:
            return None
        if hasattr(headers, "get"):
            value = headers.get(header_name) or headers.get(header_name.lower())
            if value:
                return value
        return None


class DjangoRequestWrapper(RequestWrapper):
    """Request wrapper for Django."""

    def get_url(self, request: Any) -> str | None:
        if request is None:
            return None
        if hasattr(request, "build_absolute_uri"):
            return request.build_absolute_uri()
        return None

    def get_header(self, request: Any, header_name: str) -> str | None:
        if request is None:
            return None
        if hasattr(request, "META"):
            meta_key = f"HTTP_{header_name.upper().replace('-', '_')}"
            return request.META.get(meta_key)
        return None


class AiohttpRequestWrapper(RequestWrapper):
    """Request wrapper for aiohttp."""

    def get_url(self, request: Any) -> str | None:
        if request is None:
            return None
        if hasattr(request, "url"):
            return str(request.url)
        if hasattr(request, "path"):
            return request.path
        return None

    def get_header(self, request: Any, header_name: str) -> str | None:
        if request is None:
            return None
        headers = getattr(request, "headers", None)
        if headers is None:
            return None
        if hasattr(headers, "get"):
            value = headers.get(header_name) or headers.get(header_name.lower())
            if value:
                return value
        return None


class SanicRequestWrapper(RequestWrapper):
    """Request wrapper for Sanic."""

    def get_url(self, request: Any) -> str | None:
        if request is None:
            return None
        if hasattr(request, "url"):
            return str(request.url)
        return None

    def get_header(self, request: Any, header_name: str) -> str | None:
        if request is None:
            return None
        headers = getattr(request, "headers", None)
        if headers is None:
            return None
        if hasattr(headers, "get"):
            value = headers.get(header_name) or headers.get(header_name.lower())
            if value:
                return value
        return None


class DefaultRequestWrapper(RequestWrapper):
    """Default request wrapper for unknown frameworks."""

    def get_url(self, request: Any) -> str | None:
        if request is None:
            return None
        if hasattr(request, "url"):
            return str(request.url)
        if hasattr(request, "path"):
            return request.path
        return None

    def get_header(self, request: Any, header_name: str) -> str | None:
        if request is None:
            return None
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


# Framework to wrapper class mapping
_WRAPPER_CLASSES: dict[str, type[RequestWrapper]] = {
    "starlette": StarletteRequestWrapper,
    "flask": FlaskRequestWrapper,
    "django": DjangoRequestWrapper,
    "aiohttp": AiohttpRequestWrapper,
    "sanic": SanicRequestWrapper,
    "unknown": DefaultRequestWrapper,
}


def _get_framework_from_app(app: Any) -> str:
    """Detect the web framework from app object's module."""
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


def _get_wrapper_class(framework: str) -> type[RequestWrapper]:
    """Get the appropriate wrapper class for the framework."""
    return _WRAPPER_CLASSES.get(framework, DefaultRequestWrapper)


# ============================================================================
# Cloud Logging Handler
# ============================================================================


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
        ...     app=app,
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

        # Determine framework and select wrapper class
        detected_framework = framework if framework else _get_framework_from_app(app)
        wrapper_class = _get_wrapper_class(detected_framework)
        self.request_wrapper: RequestWrapper = wrapper_class()

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
        token = self._request_ctx_var.set(request)
        request.token = token
        return token

    def reset_request(self, token: Any) -> None:
        """Reset the request context using a token.

        Args:
            token: Token returned from set_request().
        """
        try:
            self._request_ctx_var.reset(token)
        except ValueError:
            # Token was created in a different context, safe to ignore
            pass
        except Exception:
            # Silently ignore other errors to prevent logging loops
            pass

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
                    url = self.request_wrapper.get_url(request)
                    if url:
                        request_log.json_payload["url"] = url

                    if self.trace_header_name:
                        trace_header_value = self.request_wrapper.get_header(
                            request, self.trace_header_name
                        )
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
                request_log.json_payload["_messages"] = [
                    f"{datetime.now(timezone.utc).isoformat()}\t{record.levelname}\t{msg}"
                ]
            else:
                # Subsequent log - append and update severity if higher
                cur_level = getattr(logging, record.levelname)
                prev_level = getattr(logging, request_log.json_payload.get("severity", "DEBUG"))
                if cur_level > prev_level:
                    request_log.json_payload["severity"] = record.levelname

                # Ensure _messages exists before appending
                if "_messages" not in request_log.json_payload:
                    request_log.json_payload["_messages"] = []

                request_log.json_payload["_messages"].append(
                    f"{datetime.now(timezone.utc).isoformat()}\t{record.levelname}\t{msg}"
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

            # Join messages array into single string
            if "_messages" in log:
                log["message"] = "\n".join(log.pop("_messages"))

            self.stream.write(self.json.dumps(log) + self.terminator)

            if request_log.token:
                self.reset_request(request_log.token)
