from collections.abc import AsyncIterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import asyncpg
from fastapi import Request
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    SESSION_SECRET: SecretStr = Field(min_length=32)
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: SecretStr | None = None
    EMAIL_FROM: str | None = None
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    PUBLIC_BASE_URL: str = "http://127.0.0.1:8000"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
DATABASE_URL = settings.DATABASE_URL
DATABASE_DSN = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)

parts = urlsplit(DATABASE_DSN)
query = parse_qsl(parts.query, keep_blank_values=True)
sslmode = next((value for key, value in query if key == "sslmode"), None)
if sslmode is not None:
    query = [(key, value) for key, value in query if key != "sslmode"]
    query.append(("ssl", sslmode))
    DATABASE_DSN = urlunsplit(parts._replace(query=urlencode(query)))


async def get_db(request: Request) -> AsyncIterator[asyncpg.Connection]:
    async with request.app.state.pool.acquire() as connection:
        yield connection