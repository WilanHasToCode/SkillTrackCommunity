import asyncio
import hashlib
import hmac
import logging
import secrets
import smtplib
import ssl
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Literal
from urllib.parse import quote

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from database import DATABASE_DSN, get_db, settings
from learning_migration import initialize_learning_schema

SESSION_COOKIE_NAME = "skilltrack_session"
SESSION_TTL_SECONDS = 8 * 60 * 60
RESET_TOKEN_TTL = timedelta(minutes=30)
SESSION_SECRET = settings.SESSION_SECRET.get_secret_value().encode("utf-8")
logger = logging.getLogger(__name__)

SKILL_SEED = (
    ("Sports & Physical Skills", "Basketball"),
    ("Sports & Physical Skills", "Volleyball"),
    ("Sports & Physical Skills", "Badminton"),
    ("Sports & Physical Skills", "Football"),
    ("Sports & Physical Skills", "Running and Fitness"),
    ("Sports & Physical Skills", "Swimming"),
    ("Sports & Physical Skills", "Martial Arts"),
    ("Sports & Physical Skills", "Dance"),
    ("Coding & Digital Skills", "Python Programming"),
    ("Coding & Digital Skills", "HTML and CSS"),
    ("Coding & Digital Skills", "JavaScript"),
    ("Coding & Digital Skills", "Web Development"),
    ("Coding & Digital Skills", "Graphic Design"),
    ("Coding & Digital Skills", "Video Editing"),
    ("Coding & Digital Skills", "Basic Computer Skills"),
    ("Everyday & Creative Skills", "Cooking and Baking"),
    ("Everyday & Creative Skills", "Drawing and Painting"),
    ("Everyday & Creative Skills", "Photography"),
    ("Everyday & Creative Skills", "Public Speaking"),
    ("Everyday & Creative Skills", "Writing"),
    ("Everyday & Creative Skills", "Basic Financial Literacy"),
    ("Everyday & Creative Skills", "Gardening"),
    ("Everyday & Creative Skills", "First Aid"),
)

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 260_000)
    return f"{salt.hex()}:{digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt_hex, digest_hex = password_hash.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        expected_digest = bytes.fromhex(digest_hex)
    except ValueError:
        return False

    actual_digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 260_000)
    return hmac.compare_digest(actual_digest, expected_digest)


class AccountRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class RegisterRequest(AccountRequest):
    password: str = Field(min_length=12, max_length=128)
    email: str = Field(min_length=3, max_length=100)


class ProfileUpdateRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    username: str | None = Field(default=None, min_length=1, max_length=50)
    new_password: str | None = Field(default=None, min_length=12, max_length=128)


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=100)


class PasswordResetCompleteRequest(BaseModel):
    token: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class PostRequest(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


class ModuleSummary(BaseModel):
    module_id: int
    title: str
    summary: str
    sort_order: int
    completed: bool


class LessonResponse(BaseModel):
    lesson_id: int
    title: str
    body: str
    sort_order: int


class ModuleDetailResponse(BaseModel):
    module_id: int
    skill_id: int
    title: str
    summary: str
    sort_order: int
    completed: bool
    lessons: list[LessonResponse]


class AssessmentQuestionResponse(BaseModel):
    question_id: int
    question_number: int
    difficulty: Literal["beginner", "intermediate", "challenge"]
    prompt: str
    options: dict[str, str]


class AssessmentAttemptResponse(BaseModel):
    attempt_id: int
    status: Literal["in_progress", "passed", "failed"]
    questions_answered: int
    correct_answers: int
    score_percentage: int
    current_question: AssessmentQuestionResponse | None = None
    final_result: dict | None = None


class AssessmentAnswerRequest(BaseModel):
    question_id: int = Field(gt=0)
    selected_option: Literal["a", "b", "c", "d"]


class AssessmentAnswerResponse(BaseModel):
    attempt_id: int
    question_id: int
    is_correct: bool
    selected_option: str
    correct_option: str
    explanation: str
    questions_answered: int
    correct_answers: int
    status: Literal["in_progress", "passed", "failed"]
    next_question: AssessmentQuestionResponse | None = None
    final_result: dict | None = None


class ModuleProgressResponse(BaseModel):
    skill_id: int
    skill_name: str
    module_id: int
    completed: bool
    completed_attempt_id: int | None
    completed_modules: int
    total_modules: int
    progress: int
    legacy_progress: int


def create_session_token(user_id: int, expires_at: int, password_hash: str) -> str:
    claims = f"{user_id}.{expires_at}"
    signing_key = hmac.new(
        SESSION_SECRET, password_hash.encode("utf-8"), hashlib.sha256
    ).digest()
    signature = hmac.new(signing_key, claims.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{claims}.{signature}"


def should_secure_session_cookie(request: Request) -> bool:
    return settings.APP_ENV == "production" or request.url.scheme == "https"


def set_session_cookie(
    response: Response,
    request: Request,
    user_id: int,
    password_hash: str,
) -> None:
    expires_at = int(time.time()) + SESSION_TTL_SECONDS
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_session_token(user_id, expires_at, password_hash),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=should_secure_session_cookie(request),
        samesite="lax",
        path="/",
    )


def send_password_reset_email(recipient: str, reset_url: str) -> None:
    if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        raise RuntimeError("Password recovery email is not configured.")

    message = EmailMessage()
    message["Subject"] = "Reset your SkillTrack password"
    message["From"] = settings.EMAIL_FROM or settings.SMTP_USERNAME
    message["To"] = recipient
    message.set_content(
        "A password reset was requested for your SkillTrack account.\n\n"
        f"Use this one-time link within 30 minutes:\n{reset_url}\n\n"
        "If you did not request a reset, you can ignore this email."
    )

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(
            settings.SMTP_USERNAME,
            settings.SMTP_PASSWORD.get_secret_value(),
        )
        smtp.send_message(message)


async def get_current_user(
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token or len(token) > 256:
        raise HTTPException(status_code=401, detail="Authentication required.")

    try:
        user_id_text, expires_at_text, signature = token.split(".", 2)
        user_id = int(user_id_text)
        expires_at = int(expires_at_text)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")

    if user_id < 1 or expires_at <= int(time.time()):
        raise HTTPException(status_code=401, detail="Invalid or expired session.")

    user = await db.fetchrow(
        """
        SELECT user_id, username, email, password_hash, is_admin
        FROM users WHERE user_id = $1
        """,
        user_id,
    )
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")

    claims = f"{user_id}.{expires_at}"
    signing_key = hmac.new(
        SESSION_SECRET, user["password_hash"].encode("utf-8"), hashlib.sha256
    ).digest()
    expected_signature = hmac.new(
        signing_key, claims.encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=401, detail="Invalid or expired session.")

    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "email": user["email"],
        "is_admin": user["is_admin"],
    }


async def require_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    if not current_user["is_admin"]:
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return current_user


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await asyncpg.create_pool(DATABASE_DSN)
    async with app.state.pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id SERIAL PRIMARY KEY,
                    username VARCHAR(50) NOT NULL,
                    email VARCHAR(100) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    is_admin BOOLEAN NOT NULL DEFAULT FALSE
                )
                """
            )
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS posts (
                    post_id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    title VARCHAR(150) NOT NULL,
                    content TEXT,
                    is_draft BOOLEAN NOT NULL DEFAULT TRUE
                )
                """
            )
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS skills (
                    skill_id SERIAL PRIMARY KEY,
                    skill_name VARCHAR(100) NOT NULL UNIQUE,
                    category VARCHAR(50) NOT NULL DEFAULT 'Uncategorized'
                )
                """
            )
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS user_skills (
                    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    skill_id INTEGER NOT NULL REFERENCES skills(skill_id) ON DELETE CASCADE,
                    progress INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, skill_id)
                )
                """
            )
            await connection.execute(
                """
                ALTER TABLE skills
                ADD COLUMN IF NOT EXISTS category VARCHAR(50)
                """
            )
            await connection.execute(
                """
                ALTER TABLE skills
                ALTER COLUMN category SET DEFAULT 'Uncategorized'
                """
            )
            await connection.execute(
                """
                UPDATE skills
                SET category = 'Uncategorized'
                WHERE category IS NULL
                """
            )
            await connection.execute(
                """
                ALTER TABLE skills
                ALTER COLUMN category SET NOT NULL
                """
            )
            await connection.executemany(
                """
                INSERT INTO skills (skill_name, category)
                VALUES ($1, $2)
                ON CONFLICT (skill_name)
                DO UPDATE SET category = EXCLUDED.category
                """,
                [(name, category) for category, name in SKILL_SEED],
            )
            await initialize_learning_schema(connection)

    yield
    await app.state.pool.close()


app = FastAPI(title="SkillTrack Community API", lifespan=lifespan)


@app.exception_handler(asyncpg.PostgresError)
async def handle_database_error(request: Request, exc: asyncpg.PostgresError):
    logger.exception("Database operation failed.", exc_info=exc)
    return Response(
        status_code=500,
        content='{"detail":"A database error occurred. Please try again."}',
        media_type="application/json",
    )


@app.get("/")
async def root_health_check():
    return RedirectResponse(url="/Main.html")


@app.post("/auth/register", status_code=201)
async def register_account(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: asyncpg.Connection = Depends(get_db),
):
    username = payload.username.strip().casefold()
    email = payload.email.strip().casefold()
    if not username or not email:
        raise HTTPException(status_code=422, detail="Username and email are required.")

    existing = await db.fetchrow(
        "SELECT user_id FROM users WHERE lower(username) = $1 OR lower(email) = $2",
        username,
        email,
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="That username or email is already registered.")

    password_hash = hash_password(payload.password)
    user = await db.fetchrow(
        """
        INSERT INTO users (username, email, password_hash)
        VALUES ($1, $2, $3)
        RETURNING user_id, username
        """,
        username,
        email,
        password_hash,
    )
    set_session_cookie(response, request, user["user_id"], password_hash)
    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "is_admin": False,
    }


@app.post("/auth/login")
async def login(
    payload: AccountRequest,
    request: Request,
    response: Response,
    db: asyncpg.Connection = Depends(get_db),
):
    username = payload.username.strip().casefold()
    user = await db.fetchrow(
        """
        SELECT user_id, username, password_hash, is_admin
        FROM users WHERE lower(username) = $1
        """,
        username,
    )
    if user is None or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    set_session_cookie(response, request, user["user_id"], user["password_hash"])
    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "is_admin": user["is_admin"],
    }


@app.get("/auth/me")
async def get_current_account(current_user: dict = Depends(get_current_user)):
    return {
        "user_id": current_user["user_id"],
        "username": current_user["username"],
        "is_admin": current_user["is_admin"],
    }


@app.post("/auth/logout")
async def logout(request: Request, response: Response):
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        secure=should_secure_session_cookie(request),
        samesite="lax",
        path="/",
    )
    return {"status": "success"}


@app.post("/auth/forgot-password", status_code=202)
async def request_password_reset(
    payload: PasswordResetRequest,
    db: asyncpg.Connection = Depends(get_db),
):
    if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        raise HTTPException(
            status_code=503,
            detail="Password recovery email is not configured.",
        )

    email = payload.email.strip().casefold()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    reset_delivery: tuple[int, str, str, str] | None = None
    async with db.transaction():
        user = await db.fetchrow(
            "SELECT user_id, email FROM users WHERE lower(email) = $1 FOR UPDATE",
            email,
        )
        if user is not None:
            has_active_reset = await db.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM password_resets
                    WHERE user_id = $1 AND expires_at > $2
                )
                """,
                user["user_id"],
                now,
            )
            if not has_active_reset:
                token = secrets.token_urlsafe(32)
                token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
                expires_at = now + RESET_TOKEN_TTL
                await db.execute(
                    """
                    INSERT INTO password_resets (user_id, reset_code, expires_at)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (user_id)
                    DO UPDATE SET reset_code = EXCLUDED.reset_code,
                                  expires_at = EXCLUDED.expires_at
                    """,
                    user["user_id"],
                    token_hash,
                    expires_at,
                )
                reset_delivery = (user["user_id"], user["email"], token_hash, token)

    if reset_delivery is not None:
        user_id, user_email, token_hash, token = reset_delivery
        reset_url = (
            settings.PUBLIC_BASE_URL.rstrip("/")
            + "/pages/reset-password.html?token="
            + quote(token, safe="")
        )
        try:
            await asyncio.to_thread(send_password_reset_email, user_email, reset_url)
        except (OSError, smtplib.SMTPException):
            logger.exception("Could not deliver a password reset email.")
            await db.execute(
                "DELETE FROM password_resets WHERE user_id = $1 AND reset_code = $2",
                user_id,
                token_hash,
            )

    return {
        "message": "If an account matches that email, a password reset link will be sent."
    }


@app.post("/auth/reset-password")
async def complete_password_reset(
    payload: PasswordResetCompleteRequest,
    db: asyncpg.Connection = Depends(get_db),
):
    token_hash = hashlib.sha256(payload.token.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with db.transaction():
        reset = await db.fetchrow(
            """
            SELECT user_id FROM password_resets
            WHERE reset_code = $1 AND expires_at > $2
            FOR UPDATE
            """,
            token_hash,
            now,
        )
        if reset is None:
            raise HTTPException(status_code=400, detail="Reset link is invalid or expired.")

        password_hash = hash_password(payload.new_password)
        await db.execute(
            "UPDATE users SET password_hash = $1 WHERE user_id = $2",
            password_hash,
            reset["user_id"],
        )
        await db.execute(
            "DELETE FROM password_resets WHERE user_id = $1",
            reset["user_id"],
        )
    return {"message": "Password reset. You can now log in."}


@app.get("/users")
async def get_all_users(
    db: asyncpg.Connection = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    users = await db.fetch(
        "SELECT user_id, username, email, is_admin FROM users ORDER BY user_id"
    )
    return {
        "status": "success",
        "data": [
            {
                "user_id": user["user_id"],
                "username": user["username"],
                "email": user["email"],
                "is_admin": user["is_admin"],
            }
            for user in users
        ],
    }


@app.get("/users/{user_id}/profile")
async def get_user_profile(
    user_id: int,
    db: asyncpg.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if user_id != current_user["user_id"] and not current_user["is_admin"]:
        raise HTTPException(status_code=403, detail="You can only view your own profile.")

    user = await db.fetchrow(
        "SELECT user_id, username, email FROM users WHERE user_id = $1", user_id
    )
    if user is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "email": user["email"],
    }


@app.patch("/users/{user_id}/profile")
async def update_user_profile(
    user_id: int,
    payload: ProfileUpdateRequest,
    request: Request,
    response: Response,
    db: asyncpg.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if user_id != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="You can only update your own profile.")

    user = await db.fetchrow(
        "SELECT username, email, password_hash FROM users WHERE user_id = $1",
        user_id,
    )
    if user is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    if not verify_password(payload.current_password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")
    if payload.username is None and payload.new_password is None:
        raise HTTPException(
            status_code=422,
            detail="Provide a new username or a new password.",
        )

    username = user["username"]
    if payload.username is not None:
        username = payload.username.strip().casefold()
        if not username:
            raise HTTPException(status_code=422, detail="Username cannot be empty.")
        existing = await db.fetchrow(
            """
            SELECT user_id FROM users
            WHERE lower(username) = $1 AND user_id <> $2
            """,
            username,
            user_id,
        )
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail="That username is already registered.",
            )

    password_hash = (
        hash_password(payload.new_password)
        if payload.new_password is not None
        else user["password_hash"]
    )
    updated_user = await db.fetchrow(
        """
        UPDATE users SET username = $1, password_hash = $2
        WHERE user_id = $3
        RETURNING user_id, username, email
        """,
        username,
        password_hash,
        user_id,
    )
    set_session_cookie(response, request, user_id, password_hash)
    return {
        "user_id": updated_user["user_id"],
        "username": updated_user["username"],
        "email": updated_user["email"],
    }


@app.get("/skills")
async def get_skills(
    db: asyncpg.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    rows = await db.fetch(
        """
        SELECT s.skill_id, s.skill_name, s.category,
               LEAST(GREATEST(COALESCE(us.progress, 0), 0), 100) AS progress,
               LEAST(GREATEST(COALESCE(us.legacy_progress, us.progress, 0), 0), 100)
                 AS legacy_progress
        FROM skills AS s
        LEFT JOIN user_skills AS us
          ON us.skill_id = s.skill_id AND us.user_id = $1
        ORDER BY s.skill_name
        """,
        current_user["user_id"],
    )
    return [
        {
            "skill_id": row["skill_id"],
            "name": row["skill_name"],
            "category": row["category"],
            "progress": row["progress"],
            "legacy_progress": row["legacy_progress"],
        }
        for row in rows
    ]


def learning_question_response(row: asyncpg.Record) -> dict:
    return {
        "question_id": row["question_id"],
        "question_number": row["question_number"],
        "difficulty": row["difficulty"],
        "prompt": row["prompt"],
        "options": {
            "a": row["option_a"],
            "b": row["option_b"],
            "c": row["option_c"],
            "d": row["option_d"],
        },
    }


async def require_skill_module(
    db: asyncpg.Connection,
    skill_id: int,
    module_id: int,
) -> asyncpg.Record:
    module = await db.fetchrow(
        """
        SELECT s.skill_id, s.skill_name, m.module_id, m.title, m.summary, m.sort_order
        FROM skill_modules AS m
        JOIN skills AS s ON s.skill_id = m.skill_id
        WHERE s.skill_id = $1 AND m.module_id = $2
        """,
        skill_id,
        module_id,
    )
    if module is None:
        raise HTTPException(status_code=404, detail="Skill or module not found.")
    return module


async def select_attempt_question(
    db: asyncpg.Connection,
    attempt_id: int,
    module_id: int,
    question_number: int,
    difficulty: Literal["beginner", "intermediate", "challenge"],
) -> asyncpg.Record:
    question = await db.fetchrow(
        """
        SELECT q.question_id, q.question_number, q.difficulty, q.prompt,
               q.option_a, q.option_b, q.option_c, q.option_d
        FROM assessment_questions AS q
        WHERE q.module_id = $1
          AND q.is_active = TRUE
          AND q.difficulty = $2
        ORDER BY q.question_number
        LIMIT 1
        """,
        module_id,
        difficulty,
    )
    if question is None:
        raise HTTPException(
            status_code=409,
            detail="No unused question is available for this assessment step.",
        )
    await db.execute(
        """
        INSERT INTO assessment_attempt_questions (
            attempt_id, question_number, question_id, difficulty
        )
        VALUES ($1, $2, $3, $4)
        """,
        attempt_id,
        question_number,
        question["question_id"],
        difficulty,
    )
    return question


async def current_attempt_question(
    db: asyncpg.Connection,
    attempt_id: int,
    question_number: int,
) -> asyncpg.Record | None:
    row = await db.fetchrow(
        """
        SELECT aq.question_number, aq.difficulty,
               q.question_id, q.prompt, q.option_a, q.option_b,
               q.option_c, q.option_d
        FROM assessment_attempt_questions AS aq
        JOIN assessment_questions AS q ON q.question_id = aq.question_id
        WHERE aq.attempt_id = $1 AND aq.question_number = $2
        """,
        attempt_id,
        question_number,
    )
    return row


async def load_attempt_result(db: asyncpg.Connection, attempt_id: int) -> dict:
    attempt = await db.fetchrow(
        """
        SELECT status, questions_answered, correct_answers, score_percentage
        FROM assessment_attempts
        WHERE attempt_id = $1
        """,
        attempt_id,
    )
    if attempt is None:
        raise HTTPException(status_code=404, detail="Assessment attempt not found.")
    return {
        "passed": attempt["status"] == "passed",
        "correct_answers": attempt["correct_answers"],
        "questions_answered": attempt["questions_answered"],
        "total_questions": 5,
        "score_percentage": attempt["score_percentage"],
        "passing_score": 80,
        "message": (
            "Module passed. Your completion has been recorded."
            if attempt["status"] == "passed"
            else "The assessment was not passed. You can retry."
        ),
    }


@app.get("/skills/{skill_id}/modules", response_model=list[ModuleSummary])
async def list_learning_modules(
    skill_id: int,
    db: asyncpg.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    skill = await db.fetchrow("SELECT skill_id FROM skills WHERE skill_id = $1", skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found.")
    rows = await db.fetch(
        """
        SELECT m.module_id, m.title, m.summary, m.sort_order,
               EXISTS (
                   SELECT 1 FROM module_completions AS c
                   WHERE c.module_id = m.module_id AND c.user_id = $1
               ) AS completed
        FROM skill_modules AS m
        WHERE m.skill_id = $2
        ORDER BY m.sort_order
        """,
        current_user["user_id"],
        skill_id,
    )
    return [dict(row) for row in rows]


@app.get("/skills/{skill_id}/modules/{module_id}", response_model=ModuleDetailResponse)
async def get_learning_module(
    skill_id: int,
    module_id: int,
    db: asyncpg.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    module = await require_skill_module(db, skill_id, module_id)
    lessons = await db.fetch(
        """
        SELECT lesson_id, title, body, sort_order
        FROM learning_lessons
        WHERE module_id = $1
        ORDER BY sort_order
        """,
        module_id,
    )
    completed = await db.fetchval(
        """
        SELECT EXISTS (
            SELECT 1 FROM module_completions
            WHERE user_id = $1 AND module_id = $2
        )
        """,
        current_user["user_id"],
        module_id,
    )
    return {
        "module_id": module["module_id"],
        "skill_id": module["skill_id"],
        "title": module["title"],
        "summary": module["summary"],
        "sort_order": module["sort_order"],
        "completed": completed,
        "lessons": [dict(row) for row in lessons],
    }


@app.post(
    "/skills/{skill_id}/modules/{module_id}/assessment",
    response_model=AssessmentAttemptResponse,
)
async def start_or_resume_assessment(
    skill_id: int,
    module_id: int,
    db: asyncpg.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    await require_skill_module(db, skill_id, module_id)
    async with db.transaction():
        await db.execute(
            "SELECT pg_advisory_xact_lock($1, $2)",
            current_user["user_id"],
            module_id,
        )
        completed = await db.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM module_completions
                WHERE user_id = $1 AND module_id = $2
            )
            """,
            current_user["user_id"],
            module_id,
        )
        if completed:
            raise HTTPException(
                status_code=409,
                detail="This module is already completed.",
            )
        attempt = await db.fetchrow(
            """
            SELECT attempt_id, status, questions_answered, correct_answers,
                   score_percentage, current_difficulty
            FROM assessment_attempts
            WHERE user_id = $1 AND module_id = $2 AND status = 'in_progress'
            """,
            current_user["user_id"],
            module_id,
        )
        if attempt is None:
            attempt = await db.fetchrow(
                """
                INSERT INTO assessment_attempts (
                    user_id, module_id, status, current_difficulty
                )
                VALUES ($1, $2, 'in_progress', 'beginner')
                RETURNING attempt_id, status, questions_answered, correct_answers,
                          score_percentage, current_difficulty
                """,
                current_user["user_id"],
                module_id,
            )
            beginner_questions = await db.fetch(
                """
                SELECT question_id
                FROM assessment_questions
                WHERE module_id = $1 AND difficulty = 'beginner' AND is_active
                ORDER BY question_number
                LIMIT 2
                """,
                module_id,
            )
            challenge = await db.fetchrow(
                """
                SELECT question_id
                FROM assessment_questions
                WHERE module_id = $1 AND difficulty = 'challenge' AND is_active
                ORDER BY question_number
                LIMIT 1
                """,
                module_id,
            )
            if len(beginner_questions) != 2 or challenge is None:
                raise HTTPException(
                    status_code=409,
                    detail="The module assessment is not fully configured.",
                )
            await db.executemany(
                """
                INSERT INTO assessment_attempt_questions (
                    attempt_id, question_number, question_id, difficulty
                )
                VALUES ($1, $2, $3, $4)
                """,
                [
                    (attempt["attempt_id"], 1, beginner_questions[0]["question_id"], "beginner"),
                    (attempt["attempt_id"], 2, beginner_questions[1]["question_id"], "beginner"),
                    (attempt["attempt_id"], 5, challenge["question_id"], "challenge"),
                ],
            )
        next_number = attempt["questions_answered"] + 1
        question = await current_attempt_question(
            db, attempt["attempt_id"], next_number
        )
        if question is None:
            raise HTTPException(
                status_code=409,
                detail="The active attempt has no next question.",
            )
    return {
        "attempt_id": attempt["attempt_id"],
        "status": attempt["status"],
        "questions_answered": attempt["questions_answered"],
        "correct_answers": attempt["correct_answers"],
        "score_percentage": attempt["score_percentage"],
        "current_question": learning_question_response(question),
        "final_result": None,
    }


@app.get(
    "/skills/{skill_id}/modules/{module_id}/assessment/{attempt_id}",
    response_model=AssessmentAttemptResponse,
)
async def get_assessment_attempt(
    skill_id: int,
    module_id: int,
    attempt_id: int,
    db: asyncpg.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    await require_skill_module(db, skill_id, module_id)
    attempt = await db.fetchrow(
        """
        SELECT attempt_id, user_id, module_id, status, questions_answered,
               correct_answers, score_percentage
        FROM assessment_attempts
        WHERE attempt_id = $1
        """,
        attempt_id,
    )
    if attempt is None:
        raise HTTPException(status_code=404, detail="Assessment attempt not found.")
    if attempt["user_id"] != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="You cannot access another user's attempt.")
    if attempt["module_id"] != module_id:
        raise HTTPException(status_code=404, detail="Assessment attempt not found for this module.")
    response = {
        "attempt_id": attempt["attempt_id"],
        "status": attempt["status"],
        "questions_answered": attempt["questions_answered"],
        "correct_answers": attempt["correct_answers"],
        "score_percentage": attempt["score_percentage"],
        "current_question": None,
        "final_result": None,
    }
    if attempt["status"] == "in_progress":
        question = await current_attempt_question(
            db, attempt_id, attempt["questions_answered"] + 1
        )
        if question is not None:
            response["current_question"] = learning_question_response(question)
    else:
        response["final_result"] = await load_attempt_result(db, attempt_id)
    return response


@app.post(
    "/skills/{skill_id}/modules/{module_id}/assessment/{attempt_id}/answers",
    response_model=AssessmentAnswerResponse,
)
async def submit_assessment_answer(
    skill_id: int,
    module_id: int,
    attempt_id: int,
    payload: AssessmentAnswerRequest,
    db: asyncpg.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    await require_skill_module(db, skill_id, module_id)
    async with db.transaction():
        attempt = await db.fetchrow(
            """
            SELECT attempt_id, user_id, module_id, status, questions_answered,
                   correct_answers, score_percentage
            FROM assessment_attempts
            WHERE attempt_id = $1
            FOR UPDATE
            """,
            attempt_id,
        )
        if attempt is None:
            raise HTTPException(status_code=404, detail="Assessment attempt not found.")
        if attempt["user_id"] != current_user["user_id"]:
            raise HTTPException(status_code=403, detail="You cannot answer another user's attempt.")
        if attempt["module_id"] != module_id:
            raise HTTPException(status_code=404, detail="Assessment attempt not found for this module.")
        if attempt["status"] != "in_progress":
            raise HTTPException(status_code=409, detail="This assessment attempt is already completed.")

        next_number = attempt["questions_answered"] + 1
        planned = await db.fetchrow(
            """
            SELECT aq.question_number, aq.difficulty,
                   q.question_id, q.prompt, q.option_a, q.option_b,
                   q.option_c, q.option_d, q.correct_option, q.explanation
            FROM assessment_attempt_questions AS aq
            JOIN assessment_questions AS q ON q.question_id = aq.question_id
            WHERE aq.attempt_id = $1 AND aq.question_number = $2
            """,
            attempt_id,
            next_number,
        )
        if planned is None:
            raise HTTPException(status_code=409, detail="No question is ready for this attempt step.")
        if planned["question_id"] != payload.question_id:
            raise HTTPException(status_code=409, detail="The question is not the expected attempt question.")

        is_correct = payload.selected_option == planned["correct_option"]
        inserted = await db.fetchrow(
            """
            INSERT INTO assessment_attempt_answers (
                attempt_id, question_number, question_id, selected_option, is_correct
            )
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (attempt_id, question_number) DO NOTHING
            RETURNING selected_option
            """,
            attempt_id,
            next_number,
            payload.question_id,
            payload.selected_option,
            is_correct,
        )
        if inserted is None:
            raise HTTPException(status_code=409, detail="This question has already been answered.")

        questions_answered = next_number
        correct_answers = attempt["correct_answers"] + int(is_correct)
        score_percentage = round(correct_answers * 100 / 5)
        next_question = None
        final_result = None

        if questions_answered == 1:
            next_question = await current_attempt_question(db, attempt_id, 2)
        elif questions_answered == 2:
            next_difficulty = (
                "intermediate"
                if await db.fetchval(
                    """
                    SELECT coalesce(sum(a.is_correct::int), 0) * 100
                           >= (count(*) * 80)
                    FROM assessment_attempt_answers AS a
                    JOIN assessment_attempt_questions AS aq
                      ON aq.attempt_id = a.attempt_id
                     AND aq.question_id = a.question_id
                    WHERE a.attempt_id = $1 AND aq.question_number <= 2
                    """,
                    attempt_id,
                )
                else "beginner"
            )
            next_question = await select_attempt_question(
                db, attempt_id, module_id, 3, next_difficulty
            )
        elif questions_answered == 3:
            next_difficulty = (
                "intermediate"
                if await db.fetchval(
                    """
                    SELECT coalesce(sum(a.is_correct::int), 0) * 100
                           >= (count(*) * 80)
                    FROM assessment_attempt_answers AS a
                    JOIN assessment_attempt_questions AS aq
                      ON aq.attempt_id = a.attempt_id
                     AND aq.question_id = a.question_id
                    WHERE a.attempt_id = $1 AND aq.question_number <= 3
                    """,
                    attempt_id,
                )
                else "beginner"
            )
            next_question = await select_attempt_question(
                db, attempt_id, module_id, 4, next_difficulty
            )
        elif questions_answered == 4:
            next_difficulty = (
                "challenge"
                if await db.fetchval(
                    """
                    SELECT coalesce(sum(a.is_correct::int), 0) * 100
                           >= (count(*) * 80)
                    FROM assessment_attempt_answers AS a
                    JOIN assessment_attempt_questions AS aq
                      ON aq.attempt_id = a.attempt_id
                     AND aq.question_id = a.question_id
                    WHERE a.attempt_id = $1 AND aq.question_number <= 4
                    """,
                    attempt_id,
                )
                else "intermediate"
            )
            if next_difficulty == "challenge":
                await db.execute(
                    "UPDATE assessment_attempt_questions SET difficulty = 'challenge' WHERE attempt_id = $1 AND question_number = 5",
                    attempt_id,
                )
            else:
                await db.execute(
                    "DELETE FROM assessment_attempt_questions WHERE attempt_id = $1 AND question_number = 5",
                    attempt_id,
                )
                next_question = await select_attempt_question(
                    db, attempt_id, module_id, 5, next_difficulty
                )
            next_question = await current_attempt_question(db, attempt_id, 5)

        status = "in_progress"
        if questions_answered == 5:
            status = "passed" if correct_answers >= 4 else "failed"
            await db.execute(
                """
                UPDATE assessment_attempts
                SET questions_answered = $1,
                    correct_answers = $2,
                    score_percentage = $3,
                    status = $4,
                    current_difficulty = $5,
                    completed_at = now()
                WHERE attempt_id = $6
                """,
                questions_answered,
                correct_answers,
                score_percentage,
                status,
                planned["difficulty"],
                attempt_id,
            )
            if status == "passed":
                await db.execute(
                    """
                    INSERT INTO module_completions (
                        user_id, module_id, completed_attempt_id
                    )
                    VALUES ($1, $2, $3)
                    ON CONFLICT (user_id, module_id) DO NOTHING
                    """,
                    current_user["user_id"],
                    module_id,
                    attempt_id,
                )
                totals = await db.fetchrow(
                    """
                    SELECT (
                        SELECT count(*)
                        FROM skill_modules AS all_modules
                        WHERE all_modules.skill_id = skill.skill_id
                    ) AS total_modules,
                    (
                        SELECT count(*)
                        FROM module_completions AS completion
                        JOIN skill_modules AS completed_module
                          ON completed_module.module_id = completion.module_id
                        WHERE completion.user_id = $1
                          AND completed_module.skill_id = skill.skill_id
                    ) AS completed_modules
                    FROM skills AS skill
                    WHERE skill.skill_id = $2
                    """,
                    current_user["user_id"],
                    skill_id,
                )
                module_progress = round(
                    totals["completed_modules"] * 100 / totals["total_modules"]
                )
                await db.execute(
                    """
                    INSERT INTO user_skills (user_id, skill_id, progress)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (user_id, skill_id)
                    DO UPDATE SET progress = EXCLUDED.progress
                    """,
                    current_user["user_id"],
                    skill_id,
                    module_progress,
                )
            final_result = await load_attempt_result(db, attempt_id)
        else:
            await db.execute(
                """
                UPDATE assessment_attempts
                SET questions_answered = $1,
                    correct_answers = $2,
                    score_percentage = $3,
                    current_difficulty = $4
                WHERE attempt_id = $5
                """,
                questions_answered,
                correct_answers,
                score_percentage,
                next_question["difficulty"] if next_question is not None else planned["difficulty"],
                attempt_id,
            )

    return {
        "attempt_id": attempt_id,
        "question_id": payload.question_id,
        "is_correct": is_correct,
        "selected_option": payload.selected_option,
        "correct_option": planned["correct_option"],
        "explanation": planned["explanation"],
        "questions_answered": questions_answered,
        "correct_answers": correct_answers,
        "status": status,
        "next_question": (
            learning_question_response(next_question)
            if next_question is not None
            else None
        ),
        "final_result": final_result,
    }


@app.get(
    "/skills/{skill_id}/modules/{module_id}/progress",
    response_model=ModuleProgressResponse,
)
async def get_module_progress(
    skill_id: int,
    module_id: int,
    db: asyncpg.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    module = await require_skill_module(db, skill_id, module_id)
    completion = await db.fetchrow(
        """
        SELECT completed_attempt_id
        FROM module_completions
        WHERE user_id = $1 AND module_id = $2
        """,
        current_user["user_id"],
        module_id,
    )
    totals = await db.fetchrow(
        """
        SELECT (
                 SELECT count(*) FROM skill_modules WHERE skill_id = $1
               ) AS total_modules,
               (
                 SELECT count(*) FROM module_completions AS c
                 JOIN skill_modules AS m ON m.module_id = c.module_id
                 WHERE c.user_id = $2 AND m.skill_id = $1
               ) AS completed_modules
        """,
        skill_id,
        current_user["user_id"],
    )
    legacy = await db.fetchval(
        """
        SELECT coalesce(legacy_progress, progress, 0)
        FROM user_skills
        WHERE user_id = $1 AND skill_id = $2
        """,
        current_user["user_id"],
        skill_id,
    )
    completed_modules = totals["completed_modules"]
    total_modules = totals["total_modules"]
    return {
        "skill_id": skill_id,
        "skill_name": module["skill_name"],
        "module_id": module_id,
        "completed": completion is not None,
        "completed_attempt_id": (
            completion["completed_attempt_id"] if completion is not None else None
        ),
        "completed_modules": completed_modules,
        "total_modules": total_modules,
        "progress": round(completed_modules * 100 / total_modules),
        "legacy_progress": legacy or 0,
    }


@app.post(
    "/skills/{skill_id}/practice",
    status_code=410,
    responses={410: {"description": "Legacy practice endpoint retired"}},
)
async def practice_skill(
    skill_id: int,
    db: asyncpg.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    raise HTTPException(
        status_code=410,
        detail=(
            "This endpoint is retired. Use the module assessment workflow: "
            "POST /skills/{skill_id}/modules/{module_id}/assessment"
            " and submit answers through its answer endpoint."
        ),
    )


@app.get("/posts")
async def get_posts(
    db: asyncpg.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    rows = await db.fetch(
        """
        SELECT p.post_id, u.username, p.content,
               COALESCE(like_counts.likes, 0) AS likes,
               EXISTS (
                   SELECT 1 FROM interactions AS mine
                   WHERE mine.post_id = p.post_id AND mine.user_id = $1
               ) AS liked
        FROM posts AS p
        JOIN users AS u ON u.user_id = p.user_id
        LEFT JOIN (
            SELECT post_id, COUNT(*) AS likes
            FROM interactions
            GROUP BY post_id
        ) AS like_counts ON like_counts.post_id = p.post_id
        WHERE p.is_draft = FALSE
        ORDER BY p.post_id DESC
        """,
        current_user["user_id"],
    )
    return [
        {
            "id": row["post_id"],
            "author": row["username"],
            "text": row["content"] or "",
            "likes": row["likes"],
            "liked": row["liked"],
        }
        for row in rows
    ]


@app.put("/posts/{post_id}/like")
async def like_post(
    post_id: int,
    db: asyncpg.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    post = await db.fetchrow(
        "SELECT post_id FROM posts WHERE post_id = $1 AND is_draft = FALSE",
        post_id,
    )
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found.")

    await db.execute(
        """
        INSERT INTO interactions (user_id, post_id)
        VALUES ($1, $2)
        ON CONFLICT (user_id, post_id) DO NOTHING
        """,
        current_user["user_id"],
        post_id,
    )
    likes = await db.fetchval(
        "SELECT COUNT(*) FROM interactions WHERE post_id = $1", post_id
    )
    return {"id": post_id, "likes": likes, "liked": True}


@app.delete("/posts/{post_id}/like")
async def unlike_post(
    post_id: int,
    db: asyncpg.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    post = await db.fetchrow(
        "SELECT post_id FROM posts WHERE post_id = $1 AND is_draft = FALSE",
        post_id,
    )
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found.")

    await db.execute(
        "DELETE FROM interactions WHERE user_id = $1 AND post_id = $2",
        current_user["user_id"],
        post_id,
    )
    likes = await db.fetchval(
        "SELECT COUNT(*) FROM interactions WHERE post_id = $1", post_id
    )
    return {"id": post_id, "likes": likes, "liked": False}


@app.post("/posts", status_code=201)
async def create_post(
    payload: PostRequest,
    db: asyncpg.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Post content cannot be empty.")
    post = await db.fetchrow(
        """
        INSERT INTO posts (user_id, title, content, is_draft)
        VALUES ($1, $2, $3, FALSE)
        RETURNING post_id, content
        """,
        current_user["user_id"],
        content[:150],
        content,
    )
    return {
        "id": post["post_id"],
        "author": current_user["username"],
        "text": post["content"],
    }


@app.put("/posts/{post_id}")
async def update_post(
    post_id: int,
    payload: PostRequest,
    db: asyncpg.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    post = await db.fetchrow(
        "SELECT post_id, user_id FROM posts WHERE post_id = $1 AND is_draft = FALSE",
        post_id,
    )
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found.")
    if post["user_id"] != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="You can only edit your own posts.")

    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Post content cannot be empty.")
    updated_post = await db.fetchrow(
        """
        UPDATE posts SET title = $1, content = $2
        WHERE post_id = $3
        RETURNING post_id, user_id, content
        """,
        content[:150],
        content,
        post_id,
    )
    user = await db.fetchrow(
        "SELECT username FROM users WHERE user_id = $1", updated_post["user_id"]
    )
    return {
        "id": updated_post["post_id"],
        "author": user["username"],
        "text": updated_post["content"],
    }


app.mount(
    "/",
    StaticFiles(
        directory=Path(__file__).resolve().parent.parent / "frontend",
        html=True,
    ),
    name="frontend",
)