"""OpenAI Chat Completions adapter using strict JSON-schema output."""

import logging
import re

from httpx import AsyncClient
from openai import (
    APIConnectionError,
    APIError,
    APIResponseValidationError,
    APITimeoutError,
    AuthenticationError,
    AsyncOpenAI,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)

from app.schemas.evaluation import CriterionEvaluationOutput
from app.services.llm.base import (
    LLMProviderError,
    LLMTimeoutError,
    RetryableLLMError,
)

logger = logging.getLogger(__name__)
CRITERION_EVALUATION_SCHEMA = CriterionEvaluationOutput.model_json_schema(
    mode="validation"
)
_SECRET_PATTERN = re.compile(
    r"(?i)\b(?:sk-(?:proj-)?[A-Za-z0-9_*_-]{4,}|key_[A-Za-z0-9_*_-]{4,})"
)
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+\S+")
_INVALID_KEY_PATTERN = re.compile(
    r"(?i)(Incorrect API key provided:\s*)[^.]+"
)


def _sanitize_provider_message(message: object, *, api_key: str) -> str:
    sanitized = str(message or "No provider message was supplied.")
    if api_key:
        sanitized = sanitized.replace(api_key, "[REDACTED]")
    sanitized = _SECRET_PATTERN.sub("[REDACTED]", sanitized)
    sanitized = _INVALID_KEY_PATTERN.sub(r"\1[REDACTED]", sanitized)
    sanitized = _BEARER_PATTERN.sub("Bearer [REDACTED]", sanitized)
    return sanitized[:500]


def _error_fields(exc: APIError, *, api_key: str) -> dict[str, object]:
    body = getattr(exc, "body", None)
    error = body.get("error", body) if isinstance(body, dict) else {}
    if not isinstance(error, dict):
        error = {}
    provider_code = error.get("code") or getattr(exc, "code", None)
    provider_message = _sanitize_provider_message(
        error.get("message") or getattr(exc, "message", None) or type(exc).__name__,
        api_key=api_key,
    )
    return {
        "http_status": getattr(exc, "status_code", None),
        "provider_error_code": str(provider_code) if provider_code else None,
        "provider_message": provider_message,
        "exception_type": type(exc).__name__,
    }


def _log_provider_failure(
    *,
    error_code: str,
    fields: dict[str, object],
) -> None:
    logger.warning(
        "OpenAI evaluation request failed.",
        extra={
            "error_code": error_code,
            "provider_http_status": fields.get("http_status"),
            "provider_error_code": fields.get("provider_error_code"),
            "provider_exception_type": fields.get("exception_type"),
            "provider_message": fields.get("provider_message"),
        },
    )


class OpenAIProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        http_client: AsyncClient | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key
        if http_client is None:
            self._client = AsyncOpenAI(
                api_key=api_key,
                timeout=timeout_seconds,
                max_retries=0,
            )
        else:
            self._client = AsyncOpenAI(
                api_key=api_key,
                timeout=timeout_seconds,
                max_retries=0,
                http_client=http_client,
            )

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "criterion_evaluation",
                        "strict": True,
                        "schema": CRITERION_EVALUATION_SCHEMA,
                    },
                },
                temperature=0,
                max_tokens=1_500,
            )
        except APITimeoutError as exc:
            fields = _error_fields(exc, api_key=self._api_key)
            _log_provider_failure(error_code="LLM_TIMEOUT", fields=fields)
            raise LLMTimeoutError(
                "The OpenAI request timed out.",
                error_code="LLM_TIMEOUT",
                **fields,
            ) from exc
        except APIConnectionError as exc:
            fields = _error_fields(exc, api_key=self._api_key)
            _log_provider_failure(error_code="OPENAI_CONNECTION_ERROR", fields=fields)
            raise RetryableLLMError(
                "OpenAI could not be reached. Check the backend network connection.",
                error_code="OPENAI_CONNECTION_ERROR",
                **fields,
            ) from exc
        except RateLimitError as exc:
            fields = _error_fields(exc, api_key=self._api_key)
            quota_exhausted = fields["provider_error_code"] == "insufficient_quota"
            error_code = "OPENAI_QUOTA_EXCEEDED" if quota_exhausted else "OPENAI_RATE_LIMIT"
            _log_provider_failure(error_code=error_code, fields=fields)
            error_type = LLMProviderError if quota_exhausted else RetryableLLMError
            message = (
                "The OpenAI account or project has no available API quota. "
                "Check billing and usage limits."
                if quota_exhausted
                else "OpenAI rate-limited the request. Wait briefly and try again."
            )
            raise error_type(message, error_code=error_code, **fields) from exc
        except InternalServerError as exc:
            fields = _error_fields(exc, api_key=self._api_key)
            _log_provider_failure(error_code="OPENAI_SERVER_ERROR", fields=fields)
            raise RetryableLLMError(
                "OpenAI returned a temporary server error. Try again shortly.",
                error_code="OPENAI_SERVER_ERROR",
                **fields,
            ) from exc
        except AuthenticationError as exc:
            fields = _error_fields(exc, api_key=self._api_key)
            _log_provider_failure(
                error_code="OPENAI_AUTHENTICATION_ERROR",
                fields=fields,
            )
            raise LLMProviderError(
                "OpenAI rejected the configured API key. Verify it is active and belongs to the intended project.",
                error_code="OPENAI_AUTHENTICATION_ERROR",
                **fields,
            ) from exc
        except NotFoundError as exc:
            fields = _error_fields(exc, api_key=self._api_key)
            _log_provider_failure(error_code="OPENAI_MODEL_NOT_FOUND", fields=fields)
            raise LLMProviderError(
                "The configured OpenAI model was not found or is unavailable to this project.",
                error_code="OPENAI_MODEL_NOT_FOUND",
                **fields,
            ) from exc
        except PermissionDeniedError as exc:
            fields = _error_fields(exc, api_key=self._api_key)
            _log_provider_failure(error_code="OPENAI_PERMISSION_ERROR", fields=fields)
            raise LLMProviderError(
                "The configured OpenAI key does not have permission for this request.",
                error_code="OPENAI_PERMISSION_ERROR",
                **fields,
            ) from exc
        except BadRequestError as exc:
            fields = _error_fields(exc, api_key=self._api_key)
            _log_provider_failure(error_code="OPENAI_INVALID_REQUEST", fields=fields)
            raise LLMProviderError(
                "OpenAI rejected the request. Check the configured model and structured-output compatibility.",
                error_code="OPENAI_INVALID_REQUEST",
                **fields,
            ) from exc
        except APIResponseValidationError as exc:
            fields = {
                "http_status": None,
                "provider_error_code": None,
                "provider_message": _sanitize_provider_message(
                    exc, api_key=self._api_key
                ),
                "exception_type": type(exc).__name__,
            }
            _log_provider_failure(error_code="OPENAI_MALFORMED_RESPONSE", fields=fields)
            raise LLMProviderError(
                "OpenAI returned a malformed API response.",
                error_code="OPENAI_MALFORMED_RESPONSE",
                **fields,
            ) from exc
        except APIError as exc:
            fields = _error_fields(exc, api_key=self._api_key)
            _log_provider_failure(error_code="OPENAI_PROVIDER_ERROR", fields=fields)
            raise LLMProviderError(
                "OpenAI could not complete the request.",
                error_code="OPENAI_PROVIDER_ERROR",
                **fields,
            ) from exc

        if not isinstance(response.choices, list) or not response.choices:
            _log_provider_failure(
                error_code="OPENAI_MALFORMED_RESPONSE",
                fields={
                    "http_status": None,
                    "provider_error_code": None,
                    "provider_message": "The response contained no valid choices.",
                    "exception_type": "ChatCompletion",
                },
            )
            raise LLMProviderError(
                "OpenAI returned no valid completion choices.",
                error_code="OPENAI_MALFORMED_RESPONSE",
                exception_type="ChatCompletion",
                provider_message="The response contained no valid choices.",
            )
        message = getattr(response.choices[0], "message", None)
        if message is None or not isinstance(getattr(message, "content", None), (str, type(None))):
            _log_provider_failure(
                error_code="OPENAI_MALFORMED_RESPONSE",
                fields={
                    "http_status": None,
                    "provider_error_code": None,
                    "provider_message": "The first choice had an invalid message shape.",
                    "exception_type": "ChatCompletion",
                },
            )
            raise LLMProviderError(
                "OpenAI returned a malformed completion message.",
                error_code="OPENAI_MALFORMED_RESPONSE",
                exception_type="ChatCompletion",
                provider_message="The first choice had an invalid message shape.",
            )
        if getattr(message, "refusal", None):
            raise LLMProviderError(
                "OpenAI declined the evaluation request.",
                error_code="OPENAI_REFUSAL",
                exception_type="ChatCompletion",
                provider_message="The model returned a refusal.",
            )
        if not message.content:
            raise LLMProviderError(
                "OpenAI returned an empty completion.",
                error_code="OPENAI_EMPTY_RESPONSE",
                exception_type="ChatCompletion",
                provider_message="The response message contained no text.",
            )
        return message.content

    async def aclose(self) -> None:
        await self._client.close()
