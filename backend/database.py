from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

DATABASE_URL = settings.DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=True)

SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

Base = declarative_base()

async def get_db():
    async with SessionLocal() as session:
        try:
            yield session
            # If the endpoint finishes without errors, automatically save the changes
            await session.commit()
        except Exception:
            # If ANY backend error or crash happens, safely undo the broken operation
            await session.rollback()
            raise
        finally:
            # Always close the session to free up your database connection slots
            await session.close()