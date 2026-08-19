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

    # Local embeddings (ONNX INT8 keeps Railway memory usage low).
    local_embedding_model: str = "intfloat/multilingual-e5-small"
    embedding_backend: str = "onnx_int8"
    embedding_onnx_file: str = "onnx/model_qint8_avx512_vnni.onnx"
    embedding_onnx_provider: str = "CPUExecutionProvider"
    embedding_onnx_threads: int = 1
    embedding_max_length: int = 512
    embedding_batch_size: int = 16

    # Database / infrastructure
    database_url: str = (
        "postgresql+pg8000://vinpearl:vinpearl@localhost:5432/vinpearl"
    )
    db_echo: bool = False
    redis_url: str | None = None

    # Data / vector store
    data_dir: Path = Path("./data")
    chroma_dir: Path = Path("./storage/chroma_local")
    chroma_collection: str = "vinpearl_multilingual_e5_small_onnx_int8"

    # Conversation memory
    memory_enabled: bool = True
    memory_max_turns: int = 16
    memory_max_chars: int = 12000

    # RAG
    top_k: int = 10
    max_context_chars: int = 18000
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
