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

    # Tier 3 LLM categorization fallback
    llm_max_batch_size: int = 20
    llm_request_timeout_seconds: float = 30.0
    # Approximate, provider-agnostic defaults (roughly gpt-4o-mini-era pricing) —
    # override to match whatever OpenAI-compatible model is actually configured.
    llm_cost_per_1k_prompt_tokens: float = 0.00015
    llm_cost_per_1k_completion_tokens: float = 0.0006
    llm_promotion_min_occurrences: int = 3

    # Phase 6 anomaly detection — per-user IsolationForest on spending.
    # Below this many outflow transactions a user's model isn't fit at all
    # (too little history to call anything "unusual" honestly).
    anomaly_min_transactions: int = 30
    # Expected fraction of transactions that are anomalous — IsolationForest's
    # `contamination`. Deliberately low; this is a review queue, not a filter.
    anomaly_contamination: float = 0.05
    # Robust z-score a feature must reach to be named as a driver of a flag.
    anomaly_explain_z_threshold: float = 2.0

    # Phase 7 text-to-SQL ("ask your finances"). The LLM only selects a
    # reviewed query template and fills typed params — below this
    # selection confidence we decline honestly instead of guessing.
    text_to_sql_min_confidence: float = 0.6

    # Phase 8 security hardening.
    # In-process fixed-window rate limiting (no Redis — single-process
    # deployment; the store is per-worker). Disabled in the test suite.
    rate_limit_enabled: bool = True
    rate_limit_auth_max_requests: int = 10
    rate_limit_auth_window_seconds: int = 60
    rate_limit_upload_max_requests: int = 20
    rate_limit_upload_window_seconds: int = 60
    # Uploaded statement files are never served from a static path — access
    # goes through a short-lived signed token minted for the owner.
    download_url_ttl_seconds: int = 300

    # CORS: the frontend origin allowed to call this API with credentials.
    frontend_origin: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
