import asyncio
import hmac
import unittest
import uuid

import asyncpg
from fastapi.testclient import TestClient

import main
from database import DATABASE_DSN


class LoginCooldownApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        self.username = "cooldown-" + uuid.uuid4().hex[:12]
        self.password = "CorrectHorseBatteryStaple!"
        self.account_key = hmac.new(
            main.SESSION_SECRET, self.username.encode("utf-8"), "sha256"
        ).hexdigest()
        self.client.cookies.clear()
        response = self.client.post(
            "/auth/register",
            json={
                "username": self.username,
                "email": self.username + "@example.test",
                "password": self.password,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.user_id = response.json()["user_id"]
        self.client.cookies.clear()

    def tearDown(self):
        asyncio.run(self.delete_test_data())

    async def delete_test_data(self):
        connection = await asyncpg.connect(DATABASE_DSN)
        try:
            await connection.execute(
                "DELETE FROM login_attempts WHERE account_key = $1",
                self.account_key,
            )
            await connection.execute(
                "DELETE FROM users WHERE user_id = $1",
                self.user_id,
            )
        finally:
            await connection.close()

    async def expire_cooldown(self):
        connection = await asyncpg.connect(DATABASE_DSN)
        try:
            await connection.execute(
                """
                UPDATE login_attempts
                SET locked_until = clock_timestamp() - interval '1 second'
                WHERE account_key = $1
                """,
                self.account_key,
            )
        finally:
            await connection.close()

    async def read_attempt(self):
        connection = await asyncpg.connect(DATABASE_DSN)
        try:
            return await connection.fetchrow(
                """
                SELECT failed_attempts, locked_until
                FROM login_attempts
                WHERE account_key = $1
                """,
                self.account_key,
            )
        finally:
            await connection.close()

    def test_database_enforces_progressive_schedule_across_requests(self):
        schedule = (None, None, 30, 60, 120, 240, 480, 900, 900)
        for failure_number, expected_cooldown in enumerate(schedule, start=1):
            self.client.cookies.clear()
            response = self.client.post(
                "/auth/login",
                json={"username": self.username, "password": "wrong"},
            )

            if expected_cooldown is None:
                self.assertEqual(response.status_code, 401, response.text)
                self.assertEqual(
                    response.json()["detail"],
                    "Invalid username or password.",
                )
                self.assertNotIn("Retry-After", response.headers)
            else:
                self.assertEqual(response.status_code, 429, response.text)
                self.assertEqual(
                    response.json()["detail"]["retry_after_seconds"],
                    expected_cooldown,
                )
            attempt = asyncio.run(self.read_attempt())
            self.assertEqual(attempt["failed_attempts"], failure_number)
            if expected_cooldown is None:
                self.assertIsNone(attempt["locked_until"])

            if failure_number < len(schedule):
                asyncio.run(self.expire_cooldown())

    def test_successful_login_clears_persistent_failures(self):
        failed = self.client.post(
            "/auth/login",
            json={"username": self.username, "password": "wrong"},
        )
        self.assertEqual(failed.status_code, 401, failed.text)
        self.client.post(
            "/auth/login",
            json={"username": self.username, "password": "wrong"},
        )
        failed = self.client.post(
            "/auth/login",
            json={"username": self.username, "password": "wrong"},
        )
        self.assertEqual(failed.status_code, 429, failed.text)
        asyncio.run(self.expire_cooldown())

        self.client.cookies.clear()
        succeeded = self.client.post(
            "/auth/login",
            json={"username": self.username, "password": self.password},
        )

        self.assertEqual(succeeded.status_code, 200, succeeded.text)
        attempt = asyncio.run(self.read_attempt())
        self.assertEqual(attempt["failed_attempts"], 0)
        self.assertIsNone(attempt["locked_until"])

    def test_member_cannot_call_admin_data_or_mutation_endpoints(self):
        login = self.client.post(
            "/auth/login",
            json={"username": self.username, "password": self.password},
        )
        self.assertEqual(login.status_code, 200, login.text)

        users = self.client.get("/users")
        update_user = self.client.patch(
            "/admin/users/" + str(self.user_id),
            json={"username": "unauthorized-change"},
        )
        delete_post = self.client.delete("/admin/posts/1")

        self.assertEqual(users.status_code, 403)
        self.assertEqual(update_user.status_code, 403)
        self.assertEqual(delete_post.status_code, 403)

    def test_admin_can_login_and_access_admin_data(self):
        asyncio.run(self.promote_test_user())
        login = self.client.post(
            "/auth/login",
            json={"username": self.username, "password": self.password},
        )
        self.assertEqual(login.status_code, 200, login.text)
        self.assertIs(login.json()["is_admin"], True)
        self.assertEqual(self.client.get("/users").status_code, 200)

    async def promote_test_user(self):
        connection = await asyncpg.connect(DATABASE_DSN)
        try:
            await connection.execute(
                "UPDATE users SET is_admin = TRUE WHERE user_id = $1",
                self.user_id,
            )
        finally:
            await connection.close()


if __name__ == "__main__":
    unittest.main()
