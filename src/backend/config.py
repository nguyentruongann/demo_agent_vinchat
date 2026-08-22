from functools import lru_cache
from decimal import Decimal
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # LLM
    llm_model: str = "gemini/gemini-2.0-flash"
    llm_api_key: str | None = None
    llm_api_key_backup: str | None = None
    llm_base_url: str | None = None
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1500
    llm_timeout: float = 60.0
    llm_max_retries: int = 2

    # Gemini embedding contract. Keep one provider/model per collection.
    embedding_backend: str = "gemini_api"
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_api_key: str | None = None
    embedding_batch_size: int = 16
    embedding_dimension: int = 3072
    embedding_max_retries: int = 4
    embedding_retry_base_seconds: float = 1.0
    embedding_retry_max_seconds: float = 20.0

    # Database / infrastructure
    database_url: str = (
        "postgresql+pg8000://vinpearl:vinpearl@localhost:5432/vinpearl"
    )
    db_echo: bool = False
    redis_url: str | None = None

    # PostgreSQL-only knowledge source and vector store
    chroma_dir: Path = Path("./storage/chroma_local")
    chroma_collection: str = "vinpearl_gemini_embedding_001_v2"
    knowledge_manifest_name: str = "knowledge_manifest.json"
    knowledge_schema_version: int = 2
    initialize_knowledge_on_start: bool = True

    # Conversation memory
    memory_enabled: bool = True
    memory_max_turns: int = 16
    memory_max_chars: int = 12000

    # RAG
    top_k: int = 10
    max_context_chars: int = 18000
    exhaustive_max_context_chars: int = 30000
    min_relevance_score: float = 0.35

    # Price/currency presentation. This is not a live FX feed; it is a
    # configurable approximation used only to present grounded USD evidence in
    # the customer language/currency. Override USD_TO_VND_RATE in production if
    # Finance/Content updates the approved rate.
    usd_to_vnd_rate: Decimal = Decimal("26000")

    # Authentication / compatibility API
    auth_session_days: int = 7
    password_pbkdf2_iterations: int = 600000
    admin_bootstrap_key: str | None = None
    agent_api_key: str | None = None

    # API
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    expose_chat_debug: bool = False
    chat_rate_limit_per_minute: int = 30
    auth_rate_limit_per_minute: int = 12
    ticket_rate_limit_per_minute: int = 20

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: object) -> object:
        """Normalize Railway/Postgres URLs for SQLAlchemy's pg8000 driver."""
        if not isinstance(value, str):
            return value

        url = value.strip()
        if url.startswith("postgres://"):
            return "postgresql+pg8000://" + url[len("postgres://") :]
        if url.startswith("postgresql://"):
            return "postgresql+pg8000://" + url[len("postgresql://") :]
        return url

    @field_validator("embedding_backend")
    @classmethod
    def require_gemini_embedding_backend(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized != "gemini_api":
            raise ValueError("EMBEDDING_BACKEND must be gemini_api")
        return normalized


@lru_cache
def get_settings() -> Settings:
    return Settings()
