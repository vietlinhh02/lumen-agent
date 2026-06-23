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
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_timeout: int = 30

    # JWT
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24 hours

    # Semantic Scholar
    semantic_scholar_api_key: str = ""

    # PaperHub multi-source search
    paperhub_provider_names: str = "semantic_scholar,openalex,arxiv"
    paperhub_provider_timeout_seconds: float = 8.0
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
    matrix_verifier_model: str = ""

    # Matrix extraction
    # Max saved papers to process per matrix-generation run. Bump this via env
    # if you have very large projects; processing 100 papers takes ~1-2 min
    # with concurrency=8 (one LLM call per paper, plus optional verification).
    matrix_max_papers: int = 100

    # Embeddings (NVIDIA Nemotron via OpenRouter API)
    openrouter_api_key: str = ""
    embedding_provider: str = "openrouter"
    embedding_model: str = "nvidia/llama-nemotron-embed-vl-1b-v2:free"
    embedding_dimension: int = 2000  # pgvector HNSW limit; API returns 2048, truncated to 2000
    embedding_base_url: str = "https://openrouter.ai/api/v1"

    # Reranker (NVIDIA Nemotron via OpenRouter /v1/rerank)
    reranker_model: str = "nvidia/llama-nemotron-rerank-vl-1b-v2:free"
    reranker_top_n: int = 30

    # Exa
    exa_api_key: str = ""

    # Firecrawl
    firecrawl_api_key: str = ""

    # Google AI (Gemini / Gemma API)
    google_api_key: str = ""

    # Paper search defaults
    paper_search_max_results: int = 100
    paper_pdf_dir: str = "data/papers"


@lru_cache
def get_settings() -> Settings:
    """Return cached runtime settings for request handlers."""
    return Settings()
