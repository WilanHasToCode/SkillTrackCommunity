import asyncio
import hmac
import unittest
from unittest.mock import patch

from fastapi import HTTPException, Request, Response

import main


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exception_type, exception, traceback):
        return False


class FakeLoginDatabase:
    def __init__(self, user="default"):
        self.user = {
            "user_id": 7,
            "username": "member",
            "password_hash": "stored-hash",
            "is_admin": False,
        } if user == "default" else user
        self.attempts = {}
        self.user_lookup_count = 0
        self.transaction_count = 0
        self.queries = []

    def transaction(self):
        self.transaction_count += 1
        return FakeTransaction()

    async def execute(self, query, *args):
        self.queries.append(query)
        if query.lstrip().startswith("INSERT INTO login_attempts"):
            self.attempts.setdefault(
                (args[0], args[1]),
                {
                    "failed_attempts": 0,
                    "retry_after_seconds": 0,
                    "expired": False,
                    "locked_until": None,
                },
            )
        elif "SET failed_attempts = 0" in query:
            self.attempts[(args[0], args[1])] = {
                "failed_attempts": 0,
                "retry_after_seconds": 0,
                "expired": False,
                "locked_until": None,
            }
        elif "SET failed_attempts = $3" in query:
            self.attempts[(args[0], args[1])] = {
                "failed_attempts": args[2],
                "retry_after_seconds": args[3],
                "expired": False,
                "locked_until": True if args[3] else None,
            }

    async def fetchrow(self, query, *args):
        if "FROM login_attempts" in query:
            return self.attempts[(args[0], args[1])]
        if "FROM users WHERE lower(username)" in query:
            self.user_lookup_count += 1
            return self.user
        raise AssertionError("Unexpected query: " + query)


def make_request(client_ip="192.0.2.1"):
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/auth/login",
            "raw_path": b"/auth/login",
            "query_string": b"",
            "headers": [],
            "server": ("testserver", 80),
            "client": (client_ip, 1234),
        }
    )


class LoginCooldownTests(unittest.TestCase):
    def setUp(self):
        self.payload = main.AccountRequest(username="Member", password="wrong")
        self.request = make_request()
        self.account_key = hmac.new(
            main.SESSION_SECRET, b"member", "sha256"
        ).hexdigest()

    def failed_login(self, db):
        with patch.object(main, "verify_password", return_value=False):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(main.login(self.payload, self.request, Response(), db))
        return raised.exception

    def test_first_two_failures_do_not_cool_down_then_schedule_escalates(self):
        db = FakeLoginDatabase()
        attempt = None

        expected_schedule = (None, None, 30, 60, 120, 240, 480, 900, 900)
        for failure_number, expected_cooldown in enumerate(expected_schedule, start=1):
            if attempt is not None:
                attempt["retry_after_seconds"] = 0
            error = self.failed_login(db)

            attempt = db.attempts[(self.account_key, "192.0.2.1")]
            self.assertEqual(attempt["failed_attempts"], failure_number)
            if expected_cooldown is None:
                self.assertEqual(error.status_code, 401)
                self.assertEqual(error.detail, "Invalid username or password.")
                self.assertNotIn("Retry-After", error.headers or {})
                self.assertIsNone(attempt.get("locked_until"))
            else:
                self.assertEqual(error.status_code, 429)
                self.assertEqual(error.detail["retry_after_seconds"], expected_cooldown)
                self.assertEqual(error.headers["Retry-After"], str(expected_cooldown))

        self.assertTrue(any(
            "ON CONFLICT (account_key, client_ip) DO NOTHING" in query
            for query in db.queries
        ))
        self.assertEqual(db.transaction_count, len(expected_schedule))

    def test_active_cooldown_blocks_password_checks(self):
        db = FakeLoginDatabase()
        db.attempts[(self.account_key, "192.0.2.1")] = {
            "failed_attempts": 2,
            "retry_after_seconds": 18,
            "expired": False,
        }

        error = self.failed_login(db)

        self.assertEqual(error.status_code, 429)
        self.assertEqual(error.detail["retry_after_seconds"], 18)
        self.assertEqual(db.user_lookup_count, 0)

    def test_successful_login_resets_persistent_failure_counter(self):
        db = FakeLoginDatabase()
        db.attempts[(self.account_key, "192.0.2.1")] = {
            "failed_attempts": 3,
            "retry_after_seconds": 0,
            "expired": False,
        }
        response = Response()

        with patch.object(main, "verify_password", return_value=True):
            result = asyncio.run(
                main.login(self.payload, self.request, response, db)
            )

        self.assertEqual(result["user_id"], 7)
        self.assertEqual(db.attempts[(self.account_key, "192.0.2.1")]["failed_attempts"], 0)
        self.assertIn(main.SESSION_COOKIE_NAME, response.headers["set-cookie"])

    def test_unknown_and_known_accounts_receive_same_failure_response(self):
        known_error = self.failed_login(FakeLoginDatabase())
        unknown_error = self.failed_login(FakeLoginDatabase(user=None))

        self.assertEqual(known_error.status_code, unknown_error.status_code)
        self.assertEqual(known_error.detail, unknown_error.detail)

    def test_admin_data_and_mutation_routes_require_admin_dependency(self):
        protected_routes = {
            ("/users", "GET"),
            ("/admin/users/{user_id}", "PATCH"),
            ("/admin/posts/{post_id}", "DELETE"),
        }
        app_routes = {
            (route.path, method): route
            for route in main.app.routes
            for method in getattr(route, "methods", set())
        }

        for path, method in protected_routes:
            with self.subTest(path=path, method=method):
                route = app_routes[(path, method)]
                dependencies = [dependency.call for dependency in route.dependant.dependencies]
                self.assertIn(main.require_admin, dependencies)


if __name__ == "__main__":
    unittest.main()
