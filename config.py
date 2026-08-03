"""Application configuration loaded from environment variables (.env)."""
import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Mesh API (OpenAI-SDK compatible gateway)
    MESH_API_KEY: str = ""
    MESH_BASE_URL: str = "https://api.meshapi.ai/v1"
    CHAT_MODEL: str = "openai/gpt-4o-mini"
    EMBEDDING_MODEL: str = "openai/text-embedding-3-small"

    # Auth
    APP_SECRET_KEY: str = "change-me-in-production-please-use-a-long-random-string"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./smartreco.db"

    # Vector store
    CHROMA_PERSIST_PATH: str = "./chroma_db"
    CHROMA_COLLECTION_NAME: str = "products"

    # Agent
    AGENT_TRIGGER_THRESHOLD: int = 8

    # Admin seed
    ADMIN_EMAIL: str = "admin@smartreco.local"
    ADMIN_PASSWORD: str = "AdminPass123!"

    # Email / SMTP
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = "noreply@smartreco.local"
    EMAIL_ENABLED: bool = False
    DAILY_DIGEST_HOUR: int = 17
    DAILY_DIGEST_MINUTE: int = 0

    DEBUG: bool = False

    # LangSmith observability (optional bonus — tracing only activates if set)
    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_PROJECT: str = "smartreco"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

if settings.LANGCHAIN_TRACING_V2:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    if settings.LANGCHAIN_API_KEY:
        os.environ["LANGCHAIN_API_KEY"] = settings.LANGCHAIN_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = settings.LANGCHAIN_PROJECT
