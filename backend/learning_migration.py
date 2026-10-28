"""Additive, repeatable migration and seed helpers for learning content."""

from skill_content import build_learning_seed


async def create_learning_tables(connection):
    statements = (
        """
        CREATE TABLE IF NOT EXISTS skill_modules (
            module_id SERIAL PRIMARY KEY,
            skill_id INTEGER NOT NULL REFERENCES skills(skill_id) ON DELETE CASCADE,
            title VARCHAR(100) NOT NULL,
            summary TEXT NOT NULL,
            sort_order INTEGER NOT NULL CHECK (sort_order > 0),
            UNIQUE (skill_id, sort_order)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS learning_lessons (
            lesson_id SERIAL PRIMARY KEY,
            module_id INTEGER NOT NULL REFERENCES skill_modules(module_id) ON DELETE CASCADE,
            title VARCHAR(100) NOT NULL,
            body TEXT NOT NULL,
            sort_order INTEGER NOT NULL CHECK (sort_order > 0),
            UNIQUE (module_id, sort_order)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS assessment_questions (
            question_id SERIAL PRIMARY KEY,
            module_id INTEGER NOT NULL REFERENCES skill_modules(module_id) ON DELETE CASCADE,
            question_number INTEGER NOT NULL CHECK (question_number BETWEEN 1 AND 5),
            difficulty VARCHAR(20) NOT NULL CHECK (
                difficulty IN ('beginner', 'intermediate', 'challenge')
            ),
            prompt TEXT NOT NULL,
            option_a TEXT NOT NULL,
            option_b TEXT NOT NULL,
            option_c TEXT NOT NULL,
            option_d TEXT NOT NULL,
            correct_option CHAR(1) NOT NULL CHECK (correct_option IN ('a', 'b', 'c', 'd')),
            explanation TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            UNIQUE (module_id, question_number)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS assessment_attempts (
            attempt_id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            module_id INTEGER NOT NULL REFERENCES skill_modules(module_id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL CHECK (
                status IN ('in_progress', 'passed', 'failed')
            ),
            current_difficulty VARCHAR(20) NOT NULL CHECK (
                current_difficulty IN ('beginner', 'intermediate', 'challenge')
            ),
            questions_answered INTEGER NOT NULL DEFAULT 0,
            correct_answers INTEGER NOT NULL DEFAULT 0,
            score_percentage INTEGER NOT NULL DEFAULT 0,
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ,
            CHECK (questions_answered BETWEEN 0 AND 5),
            CHECK (correct_answers BETWEEN 0 AND questions_answered),
            CHECK (score_percentage BETWEEN 0 AND 100)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS assessment_attempt_questions (
            attempt_id INTEGER NOT NULL
                REFERENCES assessment_attempts(attempt_id) ON DELETE CASCADE,
            question_number INTEGER NOT NULL CHECK (question_number BETWEEN 1 AND 5),
            question_id INTEGER NOT NULL
                REFERENCES assessment_questions(question_id) ON DELETE CASCADE,
            difficulty VARCHAR(20) NOT NULL CHECK (
                difficulty IN ('beginner', 'intermediate', 'challenge')
            ),
            PRIMARY KEY (attempt_id, question_number)
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_active_attempt_per_user_module
        ON assessment_attempts (user_id, module_id)
        WHERE status = 'in_progress'
        """,
        """
        CREATE TABLE IF NOT EXISTS assessment_attempt_answers (
            attempt_id INTEGER NOT NULL REFERENCES assessment_attempts(attempt_id) ON DELETE CASCADE,
            question_number INTEGER NOT NULL CHECK (question_number BETWEEN 1 AND 5),
            question_id INTEGER NOT NULL REFERENCES assessment_questions(question_id) ON DELETE CASCADE,
            selected_option CHAR(1) NOT NULL CHECK (selected_option IN ('a', 'b', 'c', 'd')),
            is_correct BOOLEAN NOT NULL,
            answered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (attempt_id, question_number)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS module_completions (
            user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            module_id INTEGER NOT NULL REFERENCES skill_modules(module_id) ON DELETE CASCADE,
            completed_attempt_id INTEGER NOT NULL,
            completed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, module_id),
            UNIQUE (completed_attempt_id),
            FOREIGN KEY (completed_attempt_id)
                REFERENCES assessment_attempts(attempt_id) ON DELETE CASCADE
        )
        """,
    )

    for statement in statements:
        await connection.execute(statement)


async def migrate_attempt_answer_identity(connection):
    await connection.execute(
        "ALTER TABLE assessment_attempt_answers "
        "ADD COLUMN IF NOT EXISTS question_number INTEGER"
    )
    await connection.execute(
        """
        UPDATE assessment_attempt_answers AS answer
        SET question_number = plan.question_number
        FROM assessment_attempt_questions AS plan
        WHERE answer.attempt_id = plan.attempt_id
          AND answer.question_id = plan.question_id
          AND answer.question_number IS NULL
        """
    )
    await connection.execute(
        """
        ALTER TABLE assessment_attempt_answers
        ALTER COLUMN question_number SET NOT NULL
        """
    )
    has_range_check = await connection.fetchval(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conrelid = 'assessment_attempt_answers'::regclass
              AND conname = 'assessment_attempt_answers_question_number_range'
        )
        """
    )
    if not has_range_check:
        await connection.execute(
            """
            ALTER TABLE assessment_attempt_answers
            ADD CONSTRAINT assessment_attempt_answers_question_number_range
            CHECK (question_number BETWEEN 1 AND 5)
            """
        )

    primary_key_columns = await connection.fetch(
        """
        SELECT a.attname
        FROM pg_index AS i
        JOIN pg_attribute AS a
          ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        WHERE i.indrelid = 'assessment_attempt_answers'::regclass
          AND i.indisprimary
        ORDER BY array_position(i.indkey, a.attnum)
        """
    )
    columns = [row["attname"] for row in primary_key_columns]
    if columns != ["attempt_id", "question_number"]:
        await connection.execute(
            "ALTER TABLE assessment_attempt_answers "
            "DROP CONSTRAINT assessment_attempt_answers_pkey"
        )
        await connection.execute(
            "ALTER TABLE assessment_attempt_answers "
            "ADD PRIMARY KEY (attempt_id, question_number)"
        )

    plan_unique = await connection.fetchval(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conrelid = 'assessment_attempt_questions'::regclass
              AND contype = 'u'
              AND conname = 'assessment_attempt_questions_attempt_id_question_id_key'
        )
        """
    )
    if plan_unique:
        await connection.execute(
            "ALTER TABLE assessment_attempt_questions "
            "DROP CONSTRAINT assessment_attempt_questions_attempt_id_question_id_key"
        )


async def seed_learning_content(connection):
    skill_names = [row["skill_name"] for row in await connection.fetch(
        "SELECT skill_name FROM skills ORDER BY skill_id"
    )]
    modules, lessons, questions = build_learning_seed(skill_names)

    await connection.executemany(
        """
        INSERT INTO skill_modules (skill_id, sort_order, title, summary)
        SELECT skill_id, $2, $3, $4
        FROM skills
        WHERE skill_name = $1
        ON CONFLICT (skill_id, sort_order)
        DO UPDATE SET
            title = EXCLUDED.title,
            summary = EXCLUDED.summary
        """,
        modules,
    )

    module_rows = await connection.fetch(
        """
        SELECT s.skill_name, m.module_id, m.sort_order
        FROM skill_modules AS m
        JOIN skills AS s ON s.skill_id = m.skill_id
        """
    )
    module_ids = {
        (row["skill_name"], row["sort_order"]): row["module_id"]
        for row in module_rows
    }

    await connection.executemany(
        """
        INSERT INTO learning_lessons (
            module_id, title, body, sort_order
        )
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (module_id, sort_order)
        DO UPDATE SET
            title = EXCLUDED.title,
            body = EXCLUDED.body
        """,
        [
            (
                module_ids[(skill_name, module_number)],
                title,
                body,
                sort_order,
            )
            for skill_name, module_number, sort_order, title, body in lessons
        ],
    )

    await connection.executemany(
        """
        INSERT INTO assessment_questions (
            module_id, question_number, difficulty, prompt,
            option_a, option_b, option_c, option_d,
            correct_option, explanation
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        ON CONFLICT (module_id, question_number)
        DO UPDATE SET
            difficulty = EXCLUDED.difficulty,
            prompt = EXCLUDED.prompt,
            option_a = EXCLUDED.option_a,
            option_b = EXCLUDED.option_b,
            option_c = EXCLUDED.option_c,
            option_d = EXCLUDED.option_d,
            correct_option = EXCLUDED.correct_option,
            explanation = EXCLUDED.explanation,
            is_active = TRUE
        """,
        [
            (
                module_ids[(skill_name, module_number)],
                question_number,
                difficulty,
                prompt,
                option_a,
                option_b,
                option_c,
                option_d,
                correct_option,
                explanation,
            )
            for (
                skill_name,
                module_number,
                question_number,
                difficulty,
                prompt,
                option_a,
                option_b,
                option_c,
                option_d,
                correct_option,
                explanation,
            ) in questions
        ],
    )


async def initialize_learning_schema(connection):
    """Apply learning migrations and seed content without removing existing data."""
    async with connection.transaction():
        await connection.execute(
            "ALTER TABLE user_skills ADD COLUMN IF NOT EXISTS legacy_progress INTEGER"
        )
        await connection.execute(
            """
            UPDATE user_skills
            SET legacy_progress = progress
            WHERE legacy_progress IS NULL
            """
        )
        await connection.execute(
            """
            ALTER TABLE user_skills
            ALTER COLUMN legacy_progress SET DEFAULT 0
            """
        )
        await connection.execute(
            """
            ALTER TABLE user_skills
            ALTER COLUMN legacy_progress SET NOT NULL
            """
        )
        await connection.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'user_skills_legacy_progress_range'
                      AND conrelid = 'user_skills'::regclass
                ) THEN
                    ALTER TABLE user_skills
                    ADD CONSTRAINT user_skills_legacy_progress_range
                    CHECK (legacy_progress BETWEEN 0 AND 100);
                END IF;
            END $$;
            """
        )
        await create_learning_tables(connection)
        await migrate_attempt_answer_identity(connection)
        await seed_learning_content(connection)
