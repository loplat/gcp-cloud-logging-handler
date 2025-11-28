"""Tests for error_handler module."""

import pytest

# Skip tests if FastAPI is not installed
pytest.importorskip("fastapi")

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from cloud_logging_handler import CloudLoggingHandler, add_error_handler


class TestErrorHandler:
    """Test cases for error handlers."""

    def setup_method(self):
        """Set up test fixtures."""
        self.app = FastAPI()
        self.handler = CloudLoggingHandler(project="test-project")
        add_error_handler(self.app, logging_handler=self.handler)

        @self.app.get("/success")
        async def success_route():
            return {"status": "ok"}

        @self.app.get("/http-error-400")
        async def http_error_400():
            raise HTTPException(status_code=400, detail="Bad request")

        @self.app.get("/http-error-500")
        async def http_error_500():
            raise HTTPException(status_code=500, detail="Internal error")

        @self.app.get("/exception")
        async def exception_route():
            raise ValueError("Something went wrong")

        self.client = TestClient(self.app, raise_server_exceptions=False)

    def test_success_route(self):
        """Test that success routes work normally."""
        response = self.client.get("/success")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_http_exception_400(self):
        """Test handling of 4xx HTTP exceptions."""
        response = self.client.get("/http-error-400")
        assert response.status_code == 400

        data = response.json()
        assert data["error"] == "HTTPException"
        assert data["detail"] == "Bad request"

    def test_http_exception_500(self):
        """Test handling of 5xx HTTP exceptions."""
        response = self.client.get("/http-error-500")
        assert response.status_code == 500

        data = response.json()
        assert data["error"] == "HTTPException"
        assert data["detail"] == "Internal error"

    def test_generic_exception(self):
        """Test handling of generic exceptions."""
        response = self.client.get("/exception")
        assert response.status_code == 500

        data = response.json()
        assert data["error"] == "ValueError"
        assert data["detail"] == "Something went wrong"
