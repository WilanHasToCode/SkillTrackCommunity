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
from urllib.parse import quote

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from database import DATABASE_DSN, get_db, settings

SESSION_COOKIE_NAME = "skilltrack_session"
SESSION_TTL_SECONDS = 8 * 60 * 60
RESET_TOKEN_TTL = timedelta(minutes=30)
SESSION_SECRET = settings.SESSION_SECRET.get_secret_value().encode("utf-8")
logger = logging.getLogger(__name__)

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

    yield
    await app.state.pool.close()


app = FastAPI(title="SkillTrack Community API", lifespan=lifespan)


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
        SELECT s.skill_id, s.skill_name,
               LEAST(GREATEST(COALESCE(us.progress, 0), 0), 100) AS progress
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
            "progress": row["progress"],
        }
        for row in rows
    ]


@app.post("/skills/{skill_id}/practice")
async def practice_skill(
    skill_id: int,
    db: asyncpg.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    row = await db.fetchrow(
        """
        INSERT INTO user_skills (user_id, skill_id, progress)
        SELECT $1, skill_id, 10 FROM skills WHERE skill_id = $2
        ON CONFLICT (user_id, skill_id)
        DO UPDATE SET progress = LEAST(user_skills.progress + 10, 100)
        RETURNING progress
        """,
        current_user["user_id"],
        skill_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Skill not found.")
    return {"skill_id": skill_id, "progress": row["progress"]}


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