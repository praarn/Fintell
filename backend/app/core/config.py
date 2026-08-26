from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Personal Finance Statement Intelligence"
    environment: str = "development"

    database_url: str = "postgresql+asyncpg://finance:finance@localhost:5432/finance"

    jwt_secret_key: str = "dev-secret-change-me-please-this-is-not-secure-at-all"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # OpenAI-compatible LLM API, used only for Tier 3 categorization fallback
    # and text-to-SQL template selection — never for raw SQL generation.
    llm_api_key: str | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    categorization_confidence_threshold: float = 0.75

    # Tier 1 statement parsing
    upload_storage_dir: str = "uploads"
    max_upload_size_bytes: int = 15 * 1024 * 1024
    bank_profile_fuzzy_match_threshold: float = 90.0
    pdf_structure_detection_page_sample: int = 3
    ocr_min_confidence: float = 40.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
