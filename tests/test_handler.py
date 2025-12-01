"""Tests for CloudLoggingHandler."""

import io
import json
import logging

from cloud_logging_handler import CloudLoggingHandler, RequestLogs


class MockRequest:
    """Mock request object for testing."""

    def __init__(self, url: str = "http://test.com/api", headers: dict = None):
        self.url = url
        self.headers = headers or {}
        self.state = type("State", (), {"token": None})()


class TestCloudLoggingHandler:
    """Test cases for CloudLoggingHandler."""

    def setup_method(self):
        """Set up test fixtures."""
        self.stream = io.StringIO()
        self.handler = CloudLoggingHandler(
            trace_header_name="X-Cloud-Trace-Context",
            project="test-project",
        )
        self.handler.stream = self.stream

        self.logger = logging.getLogger("test_logger")
        self.logger.handlers = []
        self.logger.addHandler(self.handler)
        self.logger.setLevel(logging.DEBUG)

    def teardown_method(self):
        """Clean up after tests."""
        self.handler._request_ctx_var.set(None)
        self.logger.handlers = []

    def test_emit_without_request_context(self):
        """Test logging without request context emits plain text."""
        self.logger.info("Test message")

        output = self.stream.getvalue()
        assert output
        # Non-request context outputs plain text, not JSON
        assert output.strip() == "Test message"

    def test_emit_with_request_context(self):
        """Test logging with request context accumulates logs."""
        request = MockRequest()
        request_logs = RequestLogs(request, None)
        self.handler.set_request(request_logs)

        self.logger.info("First message")
        self.logger.warning("Second message")

        # Should not emit yet
        assert self.stream.getvalue() == ""

        # Flush to emit
        self.handler.flush()

        output = self.stream.getvalue()
        log_entry = json.loads(output.strip())

        assert log_entry["severity"] == "WARNING"  # Highest severity
        assert log_entry["url"] == "http://test.com/api"
        # Messages are concatenated in the message field
        assert "First message" in log_entry["message"]
        assert "Second message" in log_entry["message"]

    def test_trace_context_extraction(self):
        """Test extraction of trace context from headers."""
        request = MockRequest(headers={"X-Cloud-Trace-Context": "abc123/def456;o=1"})
        request_logs = RequestLogs(request, None)
        self.handler.set_request(request_logs)

        self.logger.info("Traced message")
        self.handler.flush()

        output = self.stream.getvalue()
        log_entry = json.loads(output.strip())

        assert log_entry["logging.googleapis.com/trace"] == "projects/test-project/traces/abc123"
        assert log_entry["logging.googleapis.com/spanId"] == "def456"

    def test_severity_escalation(self):
        """Test that severity escalates to highest level."""
        request = MockRequest()
        request_logs = RequestLogs(request, None)
        self.handler.set_request(request_logs)

        self.logger.debug("Debug message")
        self.logger.info("Info message")
        self.logger.error("Error message")
        self.logger.info("Another info")

        self.handler.flush()

        output = self.stream.getvalue()
        log_entry = json.loads(output.strip())

        assert log_entry["severity"] == "ERROR"

    def test_custom_json_encoder(self):
        """Test using custom JSON encoder with request context."""

        class CustomEncoder:
            @staticmethod
            def dumps(obj):
                return json.dumps({"custom": True, **obj})

        handler = CloudLoggingHandler(json_impl=CustomEncoder())
        handler.stream = io.StringIO()

        # Set up request context to trigger JSON output
        request = MockRequest()
        request_logs = RequestLogs(request, None)
        handler.set_request(request_logs)

        logger = logging.getLogger("custom_logger")
        logger.handlers = []
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        logger.info("Custom encoder test")
        handler.flush()

        output = handler.stream.getvalue()
        log_entry = json.loads(output.strip())

        assert log_entry.get("custom") is True

        # Clean up
        handler._request_ctx_var.set(None)

    def test_set_and_get_request(self):
        """Test setting and getting request context."""
        request = MockRequest()
        request_logs = RequestLogs(request, {"existing": "data"})

        token = self.handler.set_request(request_logs)
        retrieved = self.handler.get_request()

        assert retrieved is request_logs
        assert retrieved.request is request
        assert retrieved.json_payload == {"existing": "data"}

        self.handler.reset_request(token)
        assert self.handler.get_request() is None

    def test_message_format_with_timestamp(self):
        """Test that message includes timestamp and level."""
        request = MockRequest()
        request_logs = RequestLogs(request, None)
        self.handler.set_request(request_logs)

        self.logger.info("Test message")
        self.handler.flush()

        output = self.stream.getvalue()
        log_entry = json.loads(output.strip())

        # Message should contain timestamp, level, and actual message
        message = log_entry["message"]
        assert "INFO" in message
        assert "Test message" in message
        # Check for ISO timestamp format (contains T and timezone info)
        assert "T" in message


class TestRequestLogs:
    """Test cases for RequestLogs."""

    def test_request_logs_creation(self):
        """Test RequestLogs initialization."""
        request = MockRequest()
        payload = {"key": "value"}

        request_logs = RequestLogs(request, payload)

        assert request_logs.request is request
        assert request_logs.json_payload == payload

    def test_request_logs_with_none_payload(self):
        """Test RequestLogs with None payload."""
        request = MockRequest()
        request_logs = RequestLogs(request, None)

        assert request_logs.request is request
        assert request_logs.json_payload is None
