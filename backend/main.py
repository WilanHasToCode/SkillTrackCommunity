import hashlib
import hmac
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from database import DATABASE_DSN, get_db


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
    password: str = Field(min_length=3, max_length=128)


class RegisterRequest(AccountRequest):
    email: str = Field(min_length=3, max_length=100)


class ProfileUpdateRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    username: str | None = Field(default=None, min_length=1, max_length=50)
    new_password: str | None = Field(default=None, min_length=3, max_length=128)


class PostRequest(BaseModel):
    user_id: int
    content: str = Field(min_length=1, max_length=5000)


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root_health_check():
    return RedirectResponse(url="/Main.html")


@app.post("/auth/register", status_code=201)
async def register_account(payload: RegisterRequest, db: asyncpg.Connection = Depends(get_db)):
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

    user = await db.fetchrow(
        """
        INSERT INTO users (username, email, password_hash)
        VALUES ($1, $2, $3)
        RETURNING user_id, username
        """,
        username,
        email,
        hash_password(payload.password),
    )
    return {"user_id": user["user_id"], "username": user["username"]}


@app.post("/auth/login")
async def login(payload: AccountRequest, db: asyncpg.Connection = Depends(get_db)):
    username = payload.username.strip().casefold()
    user = await db.fetchrow(
        "SELECT user_id, username, password_hash FROM users WHERE lower(username) = $1",
        username,
    )
    if user is None or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    return {"user_id": user["user_id"], "username": user["username"]}


@app.get("/users")
async def get_all_users(db: asyncpg.Connection = Depends(get_db)):
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
async def get_user_profile(user_id: int, db: asyncpg.Connection = Depends(get_db)):
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
    db: asyncpg.Connection = Depends(get_db),
):
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
    return {
        "user_id": updated_user["user_id"],
        "username": updated_user["username"],
        "email": updated_user["email"],
    }


@app.get("/posts")
async def get_posts(db: asyncpg.Connection = Depends(get_db)):
    rows = await db.fetch(
        """
        SELECT p.post_id, u.username, p.content
        FROM posts AS p
        JOIN users AS u ON u.user_id = p.user_id
        WHERE p.is_draft = FALSE
        ORDER BY p.post_id DESC
        """
    )
    return [
        {
            "id": row["post_id"],
            "author": row["username"],
            "text": row["content"] or "",
        }
        for row in rows
    ]


@app.post("/posts", status_code=201)
async def create_post(payload: PostRequest, db: asyncpg.Connection = Depends(get_db)):
    user = await db.fetchrow(
        "SELECT user_id, username FROM users WHERE user_id = $1", payload.user_id
    )
    if user is None:
        raise HTTPException(status_code=404, detail="Account not found. Please log in again.")

    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Post content cannot be empty.")
    post = await db.fetchrow(
        """
        INSERT INTO posts (user_id, title, content, is_draft)
        VALUES ($1, $2, $3, FALSE)
        RETURNING post_id, content
        """,
        user["user_id"],
        content[:150],
        content,
    )
    return {
        "id": post["post_id"],
        "author": user["username"],
        "text": post["content"],
    }


@app.put("/posts/{post_id}")
async def update_post(post_id: int, payload: PostRequest, db: asyncpg.Connection = Depends(get_db)):
    post = await db.fetchrow(
        "SELECT post_id, user_id FROM posts WHERE post_id = $1 AND is_draft = FALSE",
        post_id,
    )
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found.")
    if post["user_id"] != payload.user_id:
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
        directory=Path(__file__).resolve().parent.parent / "Mainpage",
        html=True,
    ),
    name="frontend",
)