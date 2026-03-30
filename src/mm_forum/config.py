from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # PostgreSQL
    database_url: str = "postgresql://mm:changeme@localhost:5433/mm_forum"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "mm_forum_posts"

    # Embeddings
    embedding_model: Literal["local", "openai"] = "local"
    local_model_name: str = "all-MiniLM-L6-v2"
    openai_api_key: str = ""
    openai_model: str = "text-embedding-3-small"

    # LLM / RAG
    llm_provider: Literal["ollama", "openai", "anthropic"] = "anthropic"
    llm_model: str = "claude-opus-4-6"
    anthropic_api_key: str = ""
    llm_base_url: str = "http://ollama:11434"  # Ollama only
    rag_context_posts: int = 8

    # Scraper
    scrape_delay_seconds: float = 1.0
    scrape_concurrency: int = 3
    forum_base_url: str = "https://forum.mattermost.com"


settings = Settings()
