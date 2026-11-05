import asyncio
import concurrent.futures
import unittest
import uuid

import asyncpg
from fastapi.testclient import TestClient

import main
from database import DATABASE_DSN


class LearningApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        self.user_id = None
        self.client.headers.update({"origin": "http://testserver"})
        self.client.cookies.clear()

    def tearDown(self):
        if self.user_id is not None:
            asyncio.run(self.delete_user(self.user_id))

    async def delete_user(self, user_id):
        connection = await asyncpg.connect(DATABASE_DSN)
        try:
            await connection.execute("DELETE FROM users WHERE user_id = $1", user_id)
        finally:
            await connection.close()

    async def open_connection(self):
        try:
            return await asyncpg.connect(DATABASE_DSN)
        except (OSError, asyncpg.PostgresError):
            self.skipTest("PostgreSQL test database is not available")

    async def fetch_module(self, module_id):
        connection = await self.open_connection()
        try:
            return await connection.fetchrow(
                """
                SELECT m.module_id, m.skill_id, s.skill_name
                FROM skill_modules AS m
                JOIN skills AS s ON s.skill_id = m.skill_id
                WHERE m.module_id = $1
                """,
                module_id,
            )
        finally:
            await connection.close()

    async def fetch_correct_option(self, question_id):
        connection = await self.open_connection()
        try:
            return await connection.fetchval(
                "SELECT correct_option FROM assessment_questions WHERE question_id = $1",
                question_id,
            )
        finally:
            await connection.close()

    async def fetch_progress(self, user_id, skill_id):
        connection = await self.open_connection()
        try:
            row = await connection.fetchrow(
                """
                SELECT progress, legacy_progress
                FROM user_skills
                WHERE user_id = $1 AND skill_id = $2
                """,
                user_id,
                skill_id,
            )
            return None if row is None else dict(row)

        finally:
            await connection.close()

    async def fetch_historical_progress(self):
        connection = await self.open_connection()
        try:
            return await connection.fetch(
                """
                SELECT s.skill_name, us.progress, us.legacy_progress
                FROM user_skills AS us
                JOIN skills AS s ON s.skill_id = us.skill_id
                WHERE s.skill_name IN ('Basketball', 'Badminton')
                ORDER BY s.skill_name
                """
            )
        finally:
            await connection.close()

    async def fetch_attempt_count(self, user_id, module_id):
        connection = await self.open_connection()
        try:
            return await connection.fetchval(
                """
                SELECT count(*) FROM assessment_attempts
                WHERE user_id = $1 AND module_id = $2
                """,
                user_id,
                module_id,
            )
        finally:
            await connection.close()

    def register(self):
        suffix = uuid.uuid4().hex
        response = self.client.post(
            "/auth/register",
            json={
                "username": f"learning-{suffix[:12]}",
                "password": f"Password-{suffix[:16]}-!",
                "email": f"learning-{suffix}@example.invalid",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.user_id = response.json()["user_id"]
        self.credentials = {
            "username": f"learning-{suffix[:12]}",
            "password": f"Password-{suffix[:16]}-!",
        }
        return self.credentials

    def get_module(self):
        modules = self.client.get("/skills/1/modules")
        self.assertEqual(modules.status_code, 200, modules.text)
        return modules.json()[0]

    def start_attempt(self, skill_id, module_id):
        response = self.client.post(
            f"/skills/{skill_id}/modules/{module_id}/assessment"
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def submit(self, skill_id, module_id, attempt_id, question_id, selected):
        return self.client.post(
            f"/skills/{skill_id}/modules/{module_id}/assessment/{attempt_id}/answers",
            json={"question_id": question_id, "selected_option": selected},
        )

    def wrong_option(self, correct):
        return next(option for option in "abcd" if option != correct)

    def test_module_lesson_retrieval_and_reading_never_changes_progress(self):
        self.register()
        module = self.get_module()
        modules = self.client.get("/skills/999999/modules")
        self.assertEqual(modules.status_code, 404)

        module_row = asyncio.run(self.fetch_module(module["module_id"]))
        skill_id = module_row["skill_id"]
        before = asyncio.run(self.fetch_progress(self.user_id, skill_id))
        response = self.client.get(
            f"/skills/{skill_id}/modules/{module['module_id']}"
        )
        self.assertEqual(response.status_code, 200, response.text)
        detail = response.json()
        self.assertEqual(len(detail["lessons"]), 2)
        self.assertFalse(detail["completed"])
        after = asyncio.run(self.fetch_progress(self.user_id, skill_id))
        self.assertEqual(before, after)

    def test_adaptive_pass_at_eighty_and_completion_is_persistent(self):
        self.register()
        module = self.get_module()
        module_row = asyncio.run(self.fetch_module(module["module_id"]))
        skill_id = module_row["skill_id"]
        attempt = self.start_attempt(skill_id, module["module_id"])
        attempt_id = attempt["attempt_id"]
        answers = [True, True, True, False, True]

        for index, should_be_correct in enumerate(answers):
            question = attempt["current_question"]
            if question is None:
                break
            correct = asyncio.run(self.fetch_correct_option(question["question_id"]))
            selected = correct if should_be_correct else self.wrong_option(correct)
            response = self.submit(
                skill_id,
                module["module_id"],
                attempt_id,
                question["question_id"],
                selected,
            )
            self.assertEqual(response.status_code, 200, response.text)
            answer = response.json()
            self.assertEqual(answer["is_correct"], should_be_correct)
            attempt = {
                "attempt_id": attempt_id,
                "current_question": answer["next_question"],
            }
            if index == 1:
                self.assertEqual(answer["next_question"]["difficulty"], "intermediate")
            elif index == 2:
                self.assertEqual(answer["next_question"]["difficulty"], "intermediate")
            elif index == 3:
                self.assertEqual(answer["next_question"]["difficulty"], "intermediate")

        self.assertEqual(answer["status"], "passed")
        self.assertEqual(answer["final_result"]["score_percentage"], 80)
        progress = asyncio.run(self.fetch_progress(self.user_id, skill_id))
        self.assertEqual(progress["progress"], 33)

        progress_again = self.client.get(
            f"/skills/{skill_id}/modules/{module['module_id']}/progress"
        )
        self.assertEqual(progress_again.status_code, 200, progress_again.text)
        self.assertTrue(progress_again.json()["completed"])
        self.assertEqual(progress_again.json()["progress"], 33)

        duplicate = self.submit(
            skill_id,
            module["module_id"],
            attempt_id,
            answer["question_id"],
            answer["selected_option"],
        )
        self.assertEqual(duplicate.status_code, 409)
        retry = self.client.post(
            f"/skills/{skill_id}/modules/{module['module_id']}/assessment"
        )
        self.assertEqual(retry.status_code, 409)

    def test_failure_feedback_retry_and_beginner_fallback(self):
        self.register()
        module = self.get_module()
        module_row = asyncio.run(self.fetch_module(module["module_id"]))
        skill_id = module_row["skill_id"]
        attempt = self.start_attempt(skill_id, module["module_id"])

        answers = [False, False, False, False, False]
        for index, should_be_correct in enumerate(answers):
            question = attempt["current_question"]
            if question is None:
                break
            correct = asyncio.run(self.fetch_correct_option(question["question_id"]))
            response = self.submit(
                skill_id,
                module["module_id"],
                attempt["attempt_id"],
                question["question_id"],
                self.wrong_option(correct),
            )
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            self.assertFalse(body["is_correct"])
            attempt = {
                "attempt_id": attempt["attempt_id"],
                "current_question": body["next_question"],
            }
            if index == 1:
                self.assertEqual(body["next_question"]["difficulty"], "beginner")
            elif index == 2:
                self.assertEqual(body["next_question"]["difficulty"], "beginner")
            elif index == 3:
                self.assertEqual(body["next_question"]["difficulty"], "intermediate")

        self.assertEqual(body["status"], "failed")
        self.assertIn("retry", body["final_result"]["message"])

        retry = self.start_attempt(skill_id, module["module_id"])
        self.assertNotEqual(retry["attempt_id"], attempt["attempt_id"])
        self.assertEqual(asyncio.run(self.fetch_attempt_count(
            self.user_id, module["module_id"]
        )), 2)

    def test_security_validation_cross_user_and_concurrent_duplicate_answers(self):
        self.register()
        module = self.get_module()
        module_row = asyncio.run(self.fetch_module(module["module_id"]))
        skill_id = module_row["skill_id"]
        attempt = self.start_attempt(skill_id, module["module_id"])
        question = attempt["current_question"]

        owner_credentials = self.credentials
        owner_user_id = self.user_id
        suffix = uuid.uuid4().hex
        response = self.client.post(
            "/auth/register",
            json={
                "username": f"learning-other-{suffix[:8]}",
                "password": f"Password-{suffix[:16]}-!",
                "email": f"learning-other-{suffix}@example.invalid",
            },
        )
        self.assertEqual(response.status_code, 201)
        other_user_id = response.json()["user_id"]
        try:
            cross = self.client.post(
                f"/skills/{skill_id}/modules/{module['module_id']}/assessment/{attempt['attempt_id']}/answers",
                json={"question_id": question["question_id"], "selected_option": "a"},
            )
            self.assertEqual(cross.status_code, 403)

            login = self.client.post("/auth/login", json=owner_credentials)
            self.assertEqual(login.status_code, 200, login.text)
            invalid = self.submit(
                skill_id,
                module["module_id"],
                attempt["attempt_id"],
                question["question_id"],
                "z",
            )
            self.assertEqual(invalid.status_code, 422)

            wrong_module = self.submit(
                skill_id,
                module["module_id"],
                attempt["attempt_id"],
                question["question_id"] + 345,
                "a",
            )
            self.assertEqual(wrong_module.status_code, 409)

            correct = asyncio.run(self.fetch_correct_option(question["question_id"]))
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                requests = [
                    executor.submit(
                        self.submit,
                        skill_id,
                        module["module_id"],
                        attempt["attempt_id"],
                        question["question_id"],
                        correct,
                    )
                    for _ in range(2)
                ]
                statuses = sorted(request.result().status_code for request in requests)
            self.assertEqual(statuses, [200, 409])
        finally:
            asyncio.run(self.delete_user(other_user_id))
            self.user_id = owner_user_id

    def test_unauthorized_and_old_practice_endpoint_preserve_progress(self):
        self.client.cookies.clear()
        modules = self.client.get("/skills/1/modules")
        self.assertEqual(modules.status_code, 401)

        self.register()
        module = self.get_module()
        module_row = asyncio.run(self.fetch_module(module["module_id"]))
        skill_id = module_row["skill_id"]
        before = asyncio.run(self.fetch_progress(self.user_id, skill_id))
        legacy_before = asyncio.run(self.fetch_historical_progress())
        response = self.client.post(f"/skills/{skill_id}/practice")
        self.assertEqual(response.status_code, 410)
        after = asyncio.run(self.fetch_progress(self.user_id, skill_id))
        self.assertEqual(before, after)
        self.assertEqual(asyncio.run(self.fetch_historical_progress()), legacy_before)


if __name__ == "__main__":
    unittest.main()
