import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.routing import APIRoute

from app.main import app, require_vapi_auth


class VapiToolAuthTests(unittest.TestCase):
    def setUp(self):
        self.secret = "unit-test-token"

    def test_auth_is_required_on_each_tool_route(self):
        routes = {
            route.path: route
            for route in app.routes
            if isinstance(route, APIRoute) and route.path.startswith("/tools/")
        }
        self.assertEqual(
            set(routes),
            {"/tools/rate", "/tools/availability", "/tools/book"},
        )
        for path, route in routes.items():
            with self.subTest(path=path):
                self.assertTrue(
                    any(
                        dependency.call is require_vapi_auth
                        for dependency in route.dependant.dependencies
                    )
                )

    def test_missing_or_invalid_auth_is_rejected(self):
        with patch("app.main.VAPI_TOOL_SECRET", self.secret):
            for authorization in (None, "Bearer wrong-token", "Basic unit-test-token"):
                with self.subTest(authorization=authorization):
                    with self.assertRaises(HTTPException) as raised:
                        require_vapi_auth(authorization)
                    self.assertEqual(raised.exception.status_code, 401)

    def test_valid_auth_is_accepted(self):
        with patch("app.main.VAPI_TOOL_SECRET", self.secret):
            self.assertIsNone(
                require_vapi_auth(f"Bearer {self.secret}")
            )

    def test_missing_server_secret_fails_closed(self):
        with patch("app.main.VAPI_TOOL_SECRET", None):
            with self.assertRaises(HTTPException) as raised:
                require_vapi_auth(None)
        self.assertEqual(raised.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
