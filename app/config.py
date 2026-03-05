import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    autodocs_shared_secret: str = "changeme"
    ollama_api_url: str = "http://localhost:11434"
    ollama_embed_model_name: str = "embed-model"  # TODO: set to your actual Ollama embed model
    ollama_llm_model_name: str = "mistral"         # TODO: set to your actual Ollama LLM model
    pg_dsn: str = "postgresql://user:pass@db:5432/autodocs"
    embedding_dim: int = 1536
    retrieval_k: int = 5
    relevance_threshold: int = 70
    enable_langsmith: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "autodocs-layer2"
    log_level: str = "info"
    layer1_base_url: str = "http://localhost:8000"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
