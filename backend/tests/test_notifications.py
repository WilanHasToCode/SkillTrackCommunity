import asyncio
import unittest
from unittest.mock import AsyncMock

from fastapi import HTTPException, Request

import main


class FakeNotificationDb:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.fetch = AsyncMock(return_value=self.rows)
        self.execute = AsyncMock()
        self.fetchval = AsyncMock(return_value=1)
        self.fetchrow = AsyncMock(return_value={"post_id": 44})


class AdminMutationApiTests(unittest.TestCase):
    def test_admin_endpoints_require_admin_dependency(self):
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(main.require_admin({"is_admin": False}))
        self.assertEqual(raised.exception.status_code, 403)

    def test_admin_update_username_validates_and_hashes_password(self):
        db = FakeNotificationDb()
        db.fetchrow = AsyncMock(side_effect=[
            {"user_id": 5, "username": "old", "email": "x@example.com", "password_hash": "oldhash"},
            None,
            {"user_id": 5, "username": "new", "email": "x@example.com", "is_admin": False},
        ])

        result = asyncio.run(main.admin_update_user(
            5,
            main.AdminUserUpdateRequest(username="New", new_password="StrongPassword1!"),
            db,
            {"is_admin": True},
        ))

        self.assertEqual(result["username"], "new")
        password_sql = db.fetchrow.await_args_list[2].args
        self.assertNotEqual(password_sql[2], "StrongPassword1!")
        self.assertIn(":", password_sql[2])

    def test_admin_deletes_only_public_post(self):
        db = FakeNotificationDb()
        db.fetchrow = AsyncMock(return_value={"post_id": 44})

        result = asyncio.run(main.admin_delete_post(44, db, {"is_admin": True}))

        sql = db.fetchrow.await_args.args[0]
        self.assertIn("DELETE FROM posts", sql)
        self.assertIn("is_draft = FALSE", sql)
        self.assertEqual(result["post_id"], 44)


class LikeNotificationApiTests(unittest.TestCase):
    def test_notification_response_has_identity_and_post_context(self):
        db = FakeNotificationDb([
            {
                "post_id": 44,
                "liker_id": 9,
                "liker_name": "Liker",
                "post_context": "A post",
            }
        ])

        response = asyncio.run(main.get_like_notifications(db, {"user_id": 7}))

        self.assertEqual(response, [{
            "post_id": 44,
            "liker_id": 9,
            "liker_name": "Liker",
            "post_context": "A post",
        }])
        sql = db.fetch.await_args.args[0]
        self.assertIn("interaction.user_id <> $1", sql)
        self.assertIn("post.user_id = $1", sql)
        self.assertNotIn("created_at", sql)

    def test_notifications_require_authenticated_user(self):
        request = Request({"type": "http", "headers": [], "cookies": {}, "method": "GET", "path": "/notifications/likes", "query_string": b"", "scheme": "http", "server": ("test", 80), "client": ("test", 1)})

        with self.assertRaises(HTTPException) as raised:
            asyncio.run(main.get_current_user(request, FakeNotificationDb()))

        self.assertEqual(raised.exception.status_code, 401)

    def test_duplicate_like_is_still_one_active_notification(self):
        db = FakeNotificationDb([{
            "post_id": 44,
            "liker_id": 9,
            "liker_name": "Liker",
            "post_context": "A post",
        }])

        response = asyncio.run(main.get_like_notifications(db, {"user_id": 7}))

        self.assertEqual(len(response), 1)
        sql = db.fetch.await_args.args[0]
        self.assertIn("LIMIT 50", sql)

    def test_duplicate_like_and_unlike_preserve_active_state(self):
        db = FakeNotificationDb()

        liked = asyncio.run(main.like_post(44, db, {"user_id": 9}))
        like_sql = db.execute.await_args.args[0]
        self.assertEqual(liked["liked"], True)
        self.assertIn("ON CONFLICT (user_id, post_id) DO NOTHING", like_sql)
        self.assertNotIn("created_at", like_sql)

        db.execute.reset_mock()
        unliked = asyncio.run(main.unlike_post(44, db, {"user_id": 9}))
        unlike_sql = db.execute.await_args.args[0]
        self.assertEqual(unliked["liked"], False)
        self.assertIn("DELETE FROM interactions", unlike_sql)

    def test_relike_uses_existing_interactions_rows_only(self):
        db = FakeNotificationDb()

        asyncio.run(main.like_post(44, db, {"user_id": 9}))
        first_insert = db.execute.await_args.args[0]
        db.execute.reset_mock()
        asyncio.run(main.unlike_post(44, db, {"user_id": 9}))
        db.execute.reset_mock()
        asyncio.run(main.like_post(44, db, {"user_id": 9}))
        second_insert = db.execute.await_args.args[0]

        self.assertIn("INSERT INTO interactions (user_id, post_id)", first_insert)
        self.assertIn("INSERT INTO interactions (user_id, post_id)", second_insert)


if __name__ == "__main__":
    unittest.main()
