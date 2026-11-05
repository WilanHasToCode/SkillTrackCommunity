import asyncio
import os
import unittest
from http.cookies import SimpleCookie
from unittest.mock import patch

from fastapi import Request, Response

import main
from database import Settings


def make_request(scheme: str, forwarded_proto: str | None = None) -> Request:
    headers = []
    if forwarded_proto is not None:
        headers.append((b"x-forwarded-proto", forwarded_proto.encode("ascii")))
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": scheme,
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": headers,
            "server": ("testserver", 443 if scheme == "https" else 80),
            "client": ("127.0.0.1", 1234),
        }
    )


def session_cookie(response: Response) -> SimpleCookie:
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    return cookie


class SessionCookieSecurityTests(unittest.TestCase):
    def test_production_configuration_secures_cookie_behind_tls_proxy(self):
        response = Response()
        with patch.dict(os.environ, {"APP_ENV": "production"}):
            configured_settings = Settings(
                DATABASE_URL="postgresql://unused",
                SESSION_SECRET="x" * 32,
                _env_file=None,
            )
        with patch.object(main, "settings", configured_settings):
            main.set_session_cookie(
                response,
                make_request("http", forwarded_proto="http"),
                7,
                "test-password-hash",
            )

        cookie = session_cookie(response)[main.SESSION_COOKIE_NAME]
        self.assertTrue(cookie["secure"])
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "lax")
        self.assertEqual(cookie["max-age"], str(main.SESSION_TTL_SECONDS))

    def test_https_request_uses_secure_cookie_in_development(self):
        response = Response()
        with patch.object(main.settings, "APP_ENV", "development"):
            main.set_session_cookie(
                response, make_request("https"), 7, "test-password-hash"
            )

        self.assertTrue(session_cookie(response)[main.SESSION_COOKIE_NAME]["secure"])

    def test_local_http_development_does_not_set_secure_cookie(self):
        response = Response()
        with patch.object(main.settings, "APP_ENV", "development"):
            main.set_session_cookie(
                response, make_request("http"), 7, "test-password-hash"
            )

        self.assertFalse(session_cookie(response)[main.SESSION_COOKIE_NAME]["secure"])

    def test_forwarded_proto_does_not_control_development_cookie_security(self):
        response = Response()
        with patch.object(main.settings, "APP_ENV", "development"):
            main.set_session_cookie(
                response,
                make_request("http", forwarded_proto="https"),
                7,
                "test-password-hash",
            )

        self.assertFalse(session_cookie(response)[main.SESSION_COOKIE_NAME]["secure"])

    def test_production_logout_cookie_remains_secure(self):
        response = Response()
        with patch.object(main.settings, "APP_ENV", "production"):
            asyncio.run(main.logout(make_request("http"), response))

        cookie = SimpleCookie()
        cookie.load(response.headers["set-cookie"])
        deleted_cookie = cookie[main.SESSION_COOKIE_NAME]
        self.assertTrue(deleted_cookie["secure"])
        self.assertTrue(deleted_cookie["httponly"])
        self.assertEqual(deleted_cookie["samesite"], "lax")


if __name__ == "__main__":
    unittest.main()
