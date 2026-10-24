from collections.abc import AsyncIterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import asyncpg
from fastapi import Request
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
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