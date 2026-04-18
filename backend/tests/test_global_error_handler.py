"""
Tests for the global unhandled exception handler in app/main.py.

Verifies that unhandled exceptions return clean JSON 500 responses
instead of raw Python tracebacks.
"""
from __future__ import annotations

import asyncio
import json
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tests.conftest  # noqa: F401 — sets up mocks

from app.main import unhandled_exception_handler


class _FakeRequest:
    """Minimal request-like object for testing the exception handler."""
    def __init__(self, method="GET", path="/api/test"):
        self.method = method
        self.url = type("URL", (), {"path": path})()


class TestGlobalExceptionHandler(unittest.TestCase):
    """Verify the global exception handler returns clean JSON."""

    def _run_handler(self, exc, method="GET", path="/api/test"):
        req = _FakeRequest(method=method, path=path)
        loop = asyncio.new_event_loop()
        try:
            response = loop.run_until_complete(
                unhandled_exception_handler(req, exc)
            )
        finally:
            loop.close()
        return response

    def test_returns_500_status(self):
        resp = self._run_handler(ValueError("test error"))
        self.assertEqual(resp.status_code, 500)

    def test_returns_json_body(self):
        resp = self._run_handler(RuntimeError("something broke"))
        body = json.loads(resp.body)
        self.assertIn("error", body)
        self.assertEqual(body["error"], "Internal server error")
        self.assertIn("detail", body)
        self.assertIn("something broke", body["detail"])

    def test_does_not_expose_traceback_in_body(self):
        resp = self._run_handler(KeyError("secret_column"))
        body = json.loads(resp.body)
        # Body should not contain traceback frames
        self.assertNotIn("Traceback", body.get("error", ""))
        self.assertNotIn("File ", body.get("error", ""))


if __name__ == "__main__":
    unittest.main()
