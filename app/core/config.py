from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI Literature Review Assistant API"
    app_version: str = "0.1.0"
    debug: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Database
    database_url: str = "postgresql+asyncpg://litreview:litreview@localhost:5434/litreview"

    # JWT
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24 hours

    # Semantic Scholar
    semantic_scholar_api_key: str = ""

    # PaperHub multi-source search
    paperhub_provider_names: str = "semantic_scholar,openalex,arxiv,europepmc,pmc"
    paperhub_provider_timeout_seconds: float = 15.0
    paperhub_crossref_mailto: str = ""
    paperhub_openalex_email: str = ""
    paperhub_unpaywall_email: str = ""
    paperhub_core_api_key: str = ""
    paperhub_doaj_api_key: str = ""
    paperhub_zenodo_access_token: str = ""

    # AI providers
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://opencode.ai/zen/go/v1"
    default_model: str = "deepseek-v4-flash"

    # Embeddings
    embedding_provider: str = "gemini"
    google_api_key: str = ""
    gemini_embedding_model: str = "gemini-embedding-2-preview"
    gemini_embedding_dimension: int = 768

    # Paper search defaults
    paper_search_max_results: int = 100
    paper_pdf_dir: str = "data/papers"


@lru_cache
def get_settings() -> Settings:
    """Return cached runtime settings for request handlers."""
    return Settings()
