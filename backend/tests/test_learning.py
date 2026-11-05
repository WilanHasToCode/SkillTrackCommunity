import asyncio
import unittest

import asyncpg

from database import DATABASE_DSN
from learning_migration import initialize_learning_schema
from main import SKILL_SEED
from skill_content import build_learning_seed


class LearningContentTests(unittest.TestCase):
    def setUp(self):
        skill_names = [name for _category, name in SKILL_SEED]
        self.modules, self.lessons, self.questions = build_learning_seed(skill_names)

    def test_every_skill_has_three_modules_with_ordered_content(self):
        self.assertEqual(len(self.modules), 69)
        self.assertEqual(len(self.lessons), 138)
        self.assertEqual(len(self.questions), 345)

        for skill_name in [name for _category, name in SKILL_SEED]:
            module_numbers = sorted(
                number
                for name, number, _title, _summary in self.modules
                if name == skill_name
            )
            self.assertEqual(module_numbers, [1, 2, 3])

    def test_each_module_has_two_lessons_and_five_question_options(self):
        lesson_keys = [
            (skill_name, module_number)
            for skill_name, module_number, _lesson_number, _title, _body
            in self.lessons
        ]
        question_keys = [
            (skill_name, module_number)
            for skill_name, module_number, _question_number, *_question
            in self.questions
        ]

        for module in self.modules:
            skill_name, module_number, _title, _summary = module
            key = (skill_name, module_number)
            self.assertEqual(lesson_keys.count(key), 2)
            self.assertEqual(question_keys.count(key), 5)

        for _question in self.questions:
            options = _question[5:9]
            self.assertEqual(len(options), 4)
            self.assertTrue(all(option.strip() for option in options))
            self.assertIn(_question[9], {"a", "b", "c", "d"})

    def test_each_assessment_has_all_three_difficulty_levels(self):
        module_difficulties = {}
        for skill_name, module_number, _number, difficulty, *_content in self.questions:
            module_difficulties.setdefault((skill_name, module_number), []).append(difficulty)

        self.assertEqual(len(module_difficulties), 69)
        for difficulties in module_difficulties.values():
            self.assertEqual(difficulties.count("beginner"), 2)
            self.assertEqual(difficulties.count("intermediate"), 2)
            self.assertEqual(difficulties.count("challenge"), 1)


class LearningMigrationDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.connection = None

    async def open_connection(self):
        try:
            self.connection = await asyncpg.connect(DATABASE_DSN)
        except (OSError, asyncpg.PostgresError):
            self.skipTest("PostgreSQL test database is not available")

    async def close_connection(self):
        if self.connection is not None:
            await self.connection.close()

    async def snapshot(self):
        skill_rows = await self.connection.fetch(
            """
            SELECT skill_id, skill_name
            FROM skills
            ORDER BY skill_id
            """
        )
        has_legacy_progress = await self.connection.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'user_skills'
                  AND column_name = 'legacy_progress'
            )
            """
        )
        progress_rows = await self.connection.fetch(
            """
            SELECT user_id, skill_id, progress,
                   legacy_progress
            FROM user_skills
            ORDER BY user_id, skill_id
            """
            if has_legacy_progress
            else """
            SELECT user_id, skill_id, progress, progress AS legacy_progress
            FROM user_skills
            ORDER BY user_id, skill_id
            """
        )
        return (
            [(row["skill_id"], row["skill_name"]) for row in skill_rows],
            [
                (
                    row["user_id"],
                    row["skill_id"],
                    row["progress"],
                    row["legacy_progress"],
                )
                for row in progress_rows
            ],
        )

    async def run_migration_safety_check(self):
        await self.open_connection()
        try:
            before = await self.snapshot()
            dynamic_counts_before = await self.connection.fetchrow(
                """
                SELECT
                    (SELECT count(*) FROM assessment_attempts) AS attempts,
                    (SELECT count(*) FROM assessment_attempt_answers) AS answers,
                    (SELECT count(*) FROM module_completions) AS completions
                """
            )
            await initialize_learning_schema(self.connection)
            after_first = await self.snapshot()
            await initialize_learning_schema(self.connection)
            after_second = await self.snapshot()

            self.assertEqual(before, after_first)
            self.assertEqual(after_first, after_second)

            counts = await self.connection.fetchrow(
                """
                SELECT
                    (SELECT count(*) FROM skill_modules) AS modules,
                    (SELECT count(*) FROM learning_lessons) AS lessons,
                    (SELECT count(*) FROM assessment_questions) AS questions,
                    (SELECT count(*) FROM assessment_attempts) AS attempts,
                    (SELECT count(*) FROM assessment_attempt_answers) AS answers,
                    (SELECT count(*) FROM module_completions) AS completions
                """
            )
            self.assertEqual(
                {
                    key: counts[key]
                    for key in ("modules", "lessons", "questions")
                },
                {"modules": 69, "lessons": 138, "questions": 345},
            )
            self.assertEqual(
                {
                    key: counts[key]
                    for key in ("attempts", "answers", "completions")
                },
                dict(dynamic_counts_before),
            )

            learning_counts = await self.connection.fetch(
                """
                SELECT m.skill_id,
                       count(DISTINCT m.module_id) AS module_count,
                       count(DISTINCT l.lesson_id) AS lesson_count,
                       count(DISTINCT q.question_id) AS question_count
                FROM skill_modules AS m
                LEFT JOIN learning_lessons AS l ON l.module_id = m.module_id
                LEFT JOIN assessment_questions AS q ON q.module_id = m.module_id
                GROUP BY m.skill_id
                """
            )
            self.assertEqual(len(learning_counts), 23)
            self.assertTrue(all(row["module_count"] == 3 for row in learning_counts))
            self.assertTrue(all(row["lesson_count"] == 6 for row in learning_counts))
            self.assertTrue(all(row["question_count"] == 15 for row in learning_counts))

            progress = await self.connection.fetch(
                """
                SELECT skill_name, legacy_progress
                FROM user_skills
                JOIN skills USING (skill_id)
                WHERE skill_name IN ('Basketball', 'Badminton')
                ORDER BY skill_name, user_id
                """
            )
            basketball = [row["legacy_progress"] for row in progress if row["skill_name"] == "Basketball"]
            badminton = [row["legacy_progress"] for row in progress if row["skill_name"] == "Badminton"]
            self.assertIn(80, basketball)
            self.assertIn(60, badminton)
        finally:
            await self.close_connection()

    def test_migration_is_repeatable_and_preserves_existing_progress(self):
        asyncio.run(self.run_migration_safety_check())


if __name__ == "__main__":
    unittest.main()
