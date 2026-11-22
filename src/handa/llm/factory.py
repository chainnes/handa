"""Pick the chat model from the environment."""

from handa.config import Settings
from handa.errors import DeskError
from handa.llm.mock import MockModel
from handa.llm.openai_compat import OpenAIModel


def build_model(settings: Settings):
    provider = settings.llm_provider.strip().lower()
    if provider == "mock":
        return MockModel()
    if provider in {"openai", "ollama", "openai-compatible"}:
        return OpenAIModel(settings)
    raise DeskError(
        f"Unknown HANDA_LLM_PROVIDER '{settings.llm_provider}'. Use 'mock' or 'openai'.",
        500,
    )
