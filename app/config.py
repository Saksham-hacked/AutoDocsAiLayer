import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    autodocs_shared_secret: str = "changeme"
    
    # Gemini API settings
    gemini_api_key: str = ""
    gemini_llm_model_name: str = "gemini-2.5-flash"
    gemini_embed_model_name: str = "gemini-embedding-001"  # Gemini embedding model
    
    pg_dsn: str = "postgresql://user:pass@localhost:5432/autodocs"
    embedding_dim: int = 768  # gemini-embedding-001 default is 3072, but can be reduced to 768
    retrieval_k: int = 5
    relevance_threshold: int = 70
    enable_langsmith: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "autodocs-layer2"
    log_level: str = "info"
    layer1_base_url: str = "http://localhost:5000"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache(maxsize=None)
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache():
    get_settings.cache_clear()
