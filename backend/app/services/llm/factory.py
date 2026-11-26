"""Select and configure the application LLM provider."""

from app.core.config import Settings
from app.services.llm.base import LLMConfigurationError, LLMProvider
from app.services.llm.mock_provider import MockLLMProvider
from app.services.llm.openai_provider import OpenAIProvider


def create_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "mock":
        return MockLLMProvider()
    if settings.llm_provider != "openai":
        raise LLMConfigurationError(
            "LLM_PROVIDER must be explicitly configured as 'openai' or 'mock'."
        )
    api_key = (
        settings.openai_api_key.get_secret_value()
        if settings.openai_api_key
        else ""
    )
    if not api_key or not api_key.strip():
        raise LLMConfigurationError(
            "OPENAI_API_KEY is required to run an evaluation."
        )
    return OpenAIProvider(
        api_key=api_key,
        model=settings.openai_chat_model,
        timeout_seconds=settings.llm_request_timeout_seconds,
    )
