"""Integration tests for CloudLoggingHandler with real web frameworks."""

import io
import json
import logging
import uuid

import pytest

from cloud_logging_handler import CloudLoggingHandler, RequestLogs


class TestFastAPIIntegration:
    """Integration tests with FastAPI/Starlette."""

    @pytest.fixture
    def fastapi_app(self):
        """Create a FastAPI app with CloudLoggingHandler middleware."""
        from fastapi import FastAPI, Request
        from starlette.middleware.base import BaseHTTPMiddleware

        app = FastAPI()
        stream = io.StringIO()
        handler = CloudLoggingHandler(
            trace_header_name="X-Cloud-Trace-Context",
            project="test-project",
        )
        handler.stream = stream

        logger = logging.getLogger(f"fastapi_test_{uuid.uuid4().hex[:8]}")
        logger.handlers = []
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        class LoggingMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next):
                request_logs = RequestLogs(request)
                token = handler.set_request(request_logs)
                try:
                    logger.info(f"Request started: {request.url.path}")
                    response = await call_next(request)
                    logger.info(f"Request completed: {response.status_code}")
                    handler.flush()
                    return response
                finally:
                    handler.reset_request(token)

        app.add_middleware(LoggingMiddleware)

        @app.get("/test")
        async def test_endpoint():
            logger.warning("Processing test endpoint")
            return {"status": "ok"}

        @app.get("/error")
        async def error_endpoint():
            logger.error("Error occurred")
            return {"status": "error"}

        return app, handler, stream, logger

    @pytest.fixture
    def fastapi_client(self, fastapi_app):
        """Create a test client for FastAPI app."""
        from starlette.testclient import TestClient

        app, handler, stream, logger = fastapi_app
        client = TestClient(app)
        return client, handler, stream, logger

    def test_fastapi_basic_request(self, fastapi_client):
        """Test basic request logging with FastAPI."""
        client, handler, stream, logger = fastapi_client

        response = client.get("/test")
        assert response.status_code == 200

        output = stream.getvalue()
        assert output, "Log output should not be empty"

        log_entry = json.loads(output.strip())
        assert log_entry["severity"] == "WARNING"
        assert "Request started" in log_entry["message"]
        assert "Processing test endpoint" in log_entry["message"]
        assert "Request completed" in log_entry["message"]

    def test_fastapi_trace_context(self, fastapi_client):
        """Test trace context extraction with FastAPI."""
        client, handler, stream, logger = fastapi_client

        response = client.get(
            "/test",
            headers={"X-Cloud-Trace-Context": "trace123/span456;o=1"},
        )
        assert response.status_code == 200

        output = stream.getvalue()
        log_entry = json.loads(output.strip())

        assert log_entry["logging.googleapis.com/trace"] == "projects/test-project/traces/trace123"
        assert log_entry["logging.googleapis.com/spanId"] == "span456"

    def test_fastapi_url_extraction(self, fastapi_client):
        """Test URL extraction with FastAPI."""
        client, handler, stream, logger = fastapi_client

        response = client.get("/test?param=value")
        assert response.status_code == 200

        output = stream.getvalue()
        log_entry = json.loads(output.strip())

        assert "/test" in log_entry["url"]


class TestFlaskIntegration:
    """Integration tests with Flask."""

    @pytest.fixture
    def flask_app(self):
        """Create a Flask app with CloudLoggingHandler."""
        from flask import Flask, g, request

        app = Flask(__name__)
        stream = io.StringIO()
        handler = CloudLoggingHandler(
            trace_header_name="X-Cloud-Trace-Context",
            project="test-project",
        )
        handler.stream = stream

        logger = logging.getLogger(f"flask_test_{uuid.uuid4().hex[:8]}")
        logger.handlers = []
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        @app.before_request
        def before_request():
            request_logs = RequestLogs(request)
            g.log_token = handler.set_request(request_logs)
            logger.info(f"Request started: {request.path}")

        @app.after_request
        def after_request(response):
            logger.info(f"Request completed: {response.status_code}")
            handler.flush()
            return response

        @app.teardown_request
        def teardown_request(exception=None):
            if hasattr(g, "log_token"):
                handler.reset_request(g.log_token)

        @app.route("/test")
        def test_endpoint():
            logger.warning("Processing test endpoint")
            return {"status": "ok"}

        @app.route("/error")
        def error_endpoint():
            logger.error("Error occurred")
            return {"status": "error"}

        return app, handler, stream, logger

    @pytest.fixture
    def flask_client(self, flask_app):
        """Create a test client for Flask app."""
        app, handler, stream, logger = flask_app
        client = app.test_client()
        return client, handler, stream, logger

    def test_flask_basic_request(self, flask_client):
        """Test basic request logging with Flask."""
        client, handler, stream, logger = flask_client

        response = client.get("/test")
        assert response.status_code == 200

        output = stream.getvalue()
        assert output, "Log output should not be empty"

        log_entry = json.loads(output.strip())
        assert log_entry["severity"] == "WARNING"
        assert "Request started" in log_entry["message"]
        assert "Processing test endpoint" in log_entry["message"]

    def test_flask_trace_context(self, flask_client):
        """Test trace context extraction with Flask."""
        client, handler, stream, logger = flask_client

        response = client.get(
            "/test",
            headers={"X-Cloud-Trace-Context": "trace123/span456;o=1"},
        )
        assert response.status_code == 200

        output = stream.getvalue()
        log_entry = json.loads(output.strip())

        assert log_entry["logging.googleapis.com/trace"] == "projects/test-project/traces/trace123"
        assert log_entry["logging.googleapis.com/spanId"] == "span456"

    def test_flask_url_extraction(self, flask_client):
        """Test URL extraction with Flask."""
        client, handler, stream, logger = flask_client

        response = client.get("/test?param=value")
        assert response.status_code == 200

        output = stream.getvalue()
        log_entry = json.loads(output.strip())

        assert "/test" in log_entry["url"]


class TestDjangoIntegration:
    """Integration tests with Django."""

    @pytest.fixture
    def django_request_factory(self):
        """Create Django request factory and handler."""
        import django
        from django.conf import settings

        if not settings.configured:
            settings.configure(
                DEBUG=True,
                DATABASES={},
                INSTALLED_APPS=[
                    "django.contrib.contenttypes",
                    "django.contrib.auth",
                ],
                ROOT_URLCONF="",
                SECRET_KEY="test-secret-key",
                ALLOWED_HOSTS=["testserver"],
            )
            django.setup()

        from django.test import RequestFactory

        stream = io.StringIO()
        handler = CloudLoggingHandler(
            trace_header_name="X-Cloud-Trace-Context",
            project="test-project",
        )
        handler.stream = stream

        logger = logging.getLogger(f"django_test_{uuid.uuid4().hex[:8]}")
        logger.handlers = []
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        factory = RequestFactory()
        return factory, handler, stream, logger

    def test_django_basic_request(self, django_request_factory):
        """Test basic request logging with Django."""
        factory, handler, stream, logger = django_request_factory

        request = factory.get("/test", SERVER_NAME="testserver")
        request_logs = RequestLogs(request)
        token = handler.set_request(request_logs)

        try:
            logger.info("Request started")
            logger.warning("Processing request")
            logger.info("Request completed")
            handler.flush()
        finally:
            handler.reset_request(token)

        output = stream.getvalue()
        assert output, "Log output should not be empty"

        log_entry = json.loads(output.strip())
        assert log_entry["severity"] == "WARNING"
        assert "Request started" in log_entry["message"]
        assert "Processing request" in log_entry["message"]

    def test_django_trace_context(self, django_request_factory):
        """Test trace context extraction with Django."""
        factory, handler, stream, logger = django_request_factory

        request = factory.get(
            "/test",
            HTTP_X_CLOUD_TRACE_CONTEXT="trace123/span456;o=1",
            SERVER_NAME="testserver",
        )
        request_logs = RequestLogs(request)
        token = handler.set_request(request_logs)

        try:
            logger.info("Test message")
            handler.flush()
        finally:
            handler.reset_request(token)

        output = stream.getvalue()
        log_entry = json.loads(output.strip())

        assert log_entry["logging.googleapis.com/trace"] == "projects/test-project/traces/trace123"
        assert log_entry["logging.googleapis.com/spanId"] == "span456"

    def test_django_url_extraction(self, django_request_factory):
        """Test URL extraction with Django."""
        factory, handler, stream, logger = django_request_factory

        request = factory.get("/test?param=value", SERVER_NAME="testserver")
        request_logs = RequestLogs(request)
        token = handler.set_request(request_logs)

        try:
            logger.info("Test message")
            handler.flush()
        finally:
            handler.reset_request(token)

        output = stream.getvalue()
        log_entry = json.loads(output.strip())

        assert "/test" in log_entry["url"]


class TestAiohttpIntegration:
    """Integration tests with aiohttp."""

    @pytest.fixture
    def aiohttp_app(self):
        """Create an aiohttp app with CloudLoggingHandler."""
        from aiohttp import web

        stream = io.StringIO()
        log_handler = CloudLoggingHandler(
            trace_header_name="X-Cloud-Trace-Context",
            project="test-project",
        )
        log_handler.stream = stream

        logger = logging.getLogger(f"aiohttp_test_{uuid.uuid4().hex[:8]}")
        logger.handlers = []
        logger.addHandler(log_handler)
        logger.setLevel(logging.DEBUG)

        # New-style middleware for aiohttp 3.9+
        # handler is passed as keyword argument in newer versions
        @web.middleware
        async def logging_middleware(request, *, handler):
            request_logs = RequestLogs(request)
            token = log_handler.set_request(request_logs)
            try:
                logger.info(f"Request started: {request.path}")
                response = await handler(request)
                logger.info(f"Request completed: {response.status}")
                log_handler.flush()
                return response
            finally:
                log_handler.reset_request(token)

        async def test_endpoint(request):
            logger.warning("Processing test endpoint")
            return web.json_response({"status": "ok"})

        async def error_endpoint(request):
            logger.error("Error occurred")
            return web.json_response({"status": "error"})

        app = web.Application(middlewares=[logging_middleware])
        app.router.add_get("/test", test_endpoint)
        app.router.add_get("/error", error_endpoint)

        return app, log_handler, stream, logger

    @pytest.mark.asyncio
    async def test_aiohttp_basic_request(self, aiohttp_app):
        """Test basic request logging with aiohttp."""
        from aiohttp.test_utils import TestClient, TestServer

        app, handler, stream, logger = aiohttp_app

        async with TestClient(TestServer(app)) as client:
            response = await client.get("/test")
            assert response.status == 200

        output = stream.getvalue()
        assert output, "Log output should not be empty"

        log_entry = json.loads(output.strip())
        assert log_entry["severity"] == "WARNING"
        assert "Request started" in log_entry["message"]
        assert "Processing test endpoint" in log_entry["message"]

    @pytest.mark.asyncio
    async def test_aiohttp_trace_context(self, aiohttp_app):
        """Test trace context extraction with aiohttp."""
        from aiohttp.test_utils import TestClient, TestServer

        app, handler, stream, logger = aiohttp_app

        async with TestClient(TestServer(app)) as client:
            response = await client.get(
                "/test",
                headers={"X-Cloud-Trace-Context": "trace123/span456;o=1"},
            )
            assert response.status == 200

        output = stream.getvalue()
        log_entry = json.loads(output.strip())

        assert log_entry["logging.googleapis.com/trace"] == "projects/test-project/traces/trace123"
        assert log_entry["logging.googleapis.com/spanId"] == "span456"

    @pytest.mark.asyncio
    async def test_aiohttp_url_extraction(self, aiohttp_app):
        """Test URL extraction with aiohttp."""
        from aiohttp.test_utils import TestClient, TestServer

        app, handler, stream, logger = aiohttp_app

        async with TestClient(TestServer(app)) as client:
            response = await client.get("/test?param=value")
            assert response.status == 200

        output = stream.getvalue()
        log_entry = json.loads(output.strip())

        assert "/test" in log_entry["url"]


class TestSanicIntegration:
    """Integration tests with Sanic."""

    @pytest.fixture
    def sanic_app(self):
        """Create a Sanic app with CloudLoggingHandler."""
        from sanic import Sanic
        from sanic.response import json as sanic_json

        # Use unique name to avoid Sanic registration conflicts
        app_name = f"test_sanic_app_{uuid.uuid4().hex[:8]}"
        app = Sanic(app_name)

        stream = io.StringIO()
        handler = CloudLoggingHandler(
            trace_header_name="X-Cloud-Trace-Context",
            project="test-project",
        )
        handler.stream = stream

        logger = logging.getLogger(f"sanic_test_{uuid.uuid4().hex[:8]}")
        logger.handlers = []
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        @app.middleware("request")
        async def before_request(request):
            request_logs = RequestLogs(request)
            request.ctx.log_token = handler.set_request(request_logs)
            logger.info(f"Request started: {request.path}")

        @app.middleware("response")
        async def after_response(request, response):
            logger.info(f"Request completed: {response.status}")
            handler.flush()
            if hasattr(request.ctx, "log_token"):
                handler.reset_request(request.ctx.log_token)
            return response

        @app.get("/test")
        async def test_endpoint(request):
            logger.warning("Processing test endpoint")
            return sanic_json({"status": "ok"})

        @app.get("/error")
        async def error_endpoint(request):
            logger.error("Error occurred")
            return sanic_json({"status": "error"})

        return app, handler, stream, logger

    @pytest.mark.asyncio
    async def test_sanic_basic_request(self, sanic_app):
        """Test basic request logging with Sanic."""
        app, handler, stream, logger = sanic_app

        _, response = await app.asgi_client.get("/test")
        assert response.status == 200

        output = stream.getvalue()
        assert output, "Log output should not be empty"

        log_entry = json.loads(output.strip())
        assert log_entry["severity"] == "WARNING"
        assert "Request started" in log_entry["message"]
        assert "Processing test endpoint" in log_entry["message"]

    @pytest.mark.asyncio
    async def test_sanic_trace_context(self, sanic_app):
        """Test trace context extraction with Sanic."""
        app, handler, stream, logger = sanic_app

        _, response = await app.asgi_client.get(
            "/test",
            headers={"X-Cloud-Trace-Context": "trace123/span456;o=1"},
        )
        assert response.status == 200

        output = stream.getvalue()
        log_entry = json.loads(output.strip())

        assert log_entry["logging.googleapis.com/trace"] == "projects/test-project/traces/trace123"
        assert log_entry["logging.googleapis.com/spanId"] == "span456"

    @pytest.mark.asyncio
    async def test_sanic_url_extraction(self, sanic_app):
        """Test URL extraction with Sanic."""
        app, handler, stream, logger = sanic_app

        _, response = await app.asgi_client.get("/test?param=value")
        assert response.status == 200

        output = stream.getvalue()
        log_entry = json.loads(output.strip())

        assert "/test" in log_entry["url"]


class TestSeverityEscalation:
    """Test severity escalation across all frameworks."""

    @pytest.fixture
    def handler_setup(self):
        """Set up handler for severity tests."""
        stream = io.StringIO()
        handler = CloudLoggingHandler(
            trace_header_name="X-Cloud-Trace-Context",
            project="test-project",
        )
        handler.stream = stream

        logger = logging.getLogger(f"severity_test_{uuid.uuid4().hex[:8]}")
        logger.handlers = []
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        return handler, stream, logger

    def test_severity_escalation_to_error(self, handler_setup):
        """Test that severity escalates to ERROR."""
        handler, stream, logger = handler_setup

        class MockRequest:
            url = "http://test.com/api"
            headers = {}

        request = MockRequest()
        request_logs = RequestLogs(request)
        token = handler.set_request(request_logs)

        try:
            logger.debug("Debug message")
            logger.info("Info message")
            logger.error("Error message")
            logger.info("Another info")
            handler.flush()
        finally:
            handler.reset_request(token)

        output = stream.getvalue()
        log_entry = json.loads(output.strip())

        assert log_entry["severity"] == "ERROR"

    def test_severity_escalation_to_critical(self, handler_setup):
        """Test that severity escalates to CRITICAL."""
        handler, stream, logger = handler_setup

        class MockRequest:
            url = "http://test.com/api"
            headers = {}

        request = MockRequest()
        request_logs = RequestLogs(request)
        token = handler.set_request(request_logs)

        try:
            logger.info("Info message")
            logger.warning("Warning message")
            logger.critical("Critical message")
            logger.error("Error message")
            handler.flush()
        finally:
            handler.reset_request(token)

        output = stream.getvalue()
        log_entry = json.loads(output.strip())

        assert log_entry["severity"] == "CRITICAL"
