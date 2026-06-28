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
    database_url: str = "postgresql+asyncpg://litreview:litreview@127.0.0.1:5434/litreview"
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

    # Embeddings
    openrouter_api_key: str = ""
    embedding_provider: str = "openrouter"
    embedding_model: str = "nvidia/llama-nemotron-embed-vl-1b-v2:free"
    embedding_dimension: int = 2000  # pgvector HNSW limit; API returns 2048, truncated to 2000
    embedding_base_url: str = "https://openrouter.ai/api/v1"
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_embedding_dimension: int = 768  # Gemini output dim; padded to `embedding_dimension` for pgvector
    gemini_embedding_requests_per_minute: int = 100
    gemini_embedding_tokens_per_minute: int = 30_000

    # Jina AI (https://jina.ai/api-dashboard/embedding)
    # Used by both the embedding service (provider="jina") and the reranker
    # service (auto-preferred when set). Embeddings use Matryoshka MRL so
    # `jina_embedding_dimension` can be smaller than the model's native dim.
    jina_api_key: str = ""
    jina_embedding_url: str = "https://api.jina.ai/v1/embeddings"
    jina_embedding_model: str = "jina-embeddings-v3"
    jina_embedding_dimension: int = 1024  # MRL dim: 32/64/128/256/512/768/1024
    jina_embedding_task_query: str = "retrieval.query"
    jina_embedding_task_passage: str = "retrieval.passage"
    jina_embedding_requests_per_minute: int = 100  # free-tier limit
    jina_rerank_url: str = "https://api.jina.ai/v1/rerank"
    jina_rerank_model: str = "jina-reranker-v2-base-multilingual"
    jina_rerank_requests_per_minute: int = 100  # free-tier limit

    # Reranker (OpenRouter /v1/rerank). Nemotron free tier is no longer
    # available on OpenRouter (404), so we default to Cohere v3.5 which
    # is the only model we verified works on this endpoint today.
    reranker_model: str = "cohere/rerank-v3.5"
    reranker_top_n: int = 30

    # Exa
    exa_api_key: str = ""

    # Firecrawl
    firecrawl_api_key: str = ""

    # Google AI (Gemini / Gemma API)
    google_api_key: str = ""

    # Cohere (used for free-tier rerank via api.cohere.com/v2/rerank).
    # Kept as a fallback when JINA_API_KEY is not set; Jina is preferred
    # because its free tier is 10x larger (100 RPM vs 10 RPM).
    cohere_api_key: str = ""
    cohere_rerank_model: str = "rerank-english-v3.0"
    cohere_rerank_url: str = "https://api.cohere.com/v2/rerank"
    cohere_rerank_requests_per_minute: int = 10  # free trial tier limit

    # Paper search defaults
    paper_search_max_results: int = 100
    paper_pdf_dir: str = "data/papers"


@lru_cache
def get_settings() -> Settings:
    """Return cached runtime settings for request handlers."""
    return Settings()
