"""Provider-neutral LLM contracts and safe error types."""

from typing import Protocol


class LLMConfigurationError(RuntimeError):
    """Raised when the selected provider is not configured."""


class LLMProviderError(RuntimeError):
    """Raised when a provider cannot produce a usable response."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        http_status: int | None = None,
        provider_error_code: str | None = None,
        provider_message: str | None = None,
        exception_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.http_status = http_status
        self.provider_error_code = provider_error_code
        self.provider_message = provider_message
        self.exception_type = exception_type


class RetryableLLMError(LLMProviderError):
    """Raised for transient provider errors that may succeed on retry."""


class LLMTimeoutError(RetryableLLMError):
    """Raised when the provider request times out."""


class InvalidLLMOutputError(RuntimeError):
    """Raised when a provider response cannot satisfy the output schema."""


class InvalidLLMScoreError(RuntimeError):
    """Raised when the provider repeatedly returns an out-of-range score."""


class InvalidLLMEvidenceError(RuntimeError):
    """Raised when provider-generated evidence cannot be verified."""


class LLMProvider(Protocol):
    async def complete(self, *, system_prompt: str, user_prompt: str) -> str: ...

    async def aclose(self) -> None: ...
