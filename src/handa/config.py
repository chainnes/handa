"""Runtime settings. Secrets come from the environment, never from code."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HANDA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: str = "mock"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_timeout_s: float = 40
    embeddings: str = "hash"
    data_dir: Path = Path(".handa")
    host: str = "0.0.0.0"
    port: int = 43123
    log_level: str = "INFO"
    max_revisions: int = 2

    @property
    def provider_label(self) -> str:
        if self.llm_provider == "mock":
            return "mock"
        return f"{self.llm_provider}:{self.llm_model}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
