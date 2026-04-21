from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.llm_config import (
    DeepSeekConfigError,
    get_deepseek_timeout_seconds,
    load_deepseek_api_key,
)


DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"


class DeepSeekClientError(RuntimeError):
    """Base DeepSeek client error."""


class DeepSeekConfigurationError(DeepSeekClientError):
    """Raised when the SDK or key configuration is unavailable."""


class DeepSeekTimeoutError(DeepSeekClientError):
    """Raised when DeepSeek does not answer before the timeout."""


class DeepSeekInvocationError(DeepSeekClientError):
    """Raised when the remote DeepSeek invocation fails."""


class DeepSeekEmptyResponseError(DeepSeekClientError):
    """Raised when DeepSeek returns no usable content."""


@dataclass(frozen=True, slots=True)
class DeepSeekChatCompletionResult:
    content: str
    model: str | None = None
    response_id: str | None = None
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None


class DeepSeekChatClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = DEFAULT_DEEPSEEK_MODEL,
        timeout_seconds: float | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def _resolve_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        try:
            return load_deepseek_api_key()
        except DeepSeekConfigError as exc:
            raise DeepSeekConfigurationError(str(exc)) from exc

    def _resolve_timeout_seconds(self) -> float:
        if self.timeout_seconds is not None:
            return self.timeout_seconds
        try:
            return get_deepseek_timeout_seconds()
        except DeepSeekConfigError as exc:
            raise DeepSeekConfigurationError(str(exc)) from exc

    @staticmethod
    def _flatten_message_content(content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            fragments: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    fragments.append(str(item.get("text") or "").strip())
                elif isinstance(item, str):
                    fragments.append(item.strip())
            return "\n".join(fragment for fragment in fragments if fragment).strip()
        return str(content).strip()

    def create_chat_completion(
        self,
        *,
        messages: list[dict[str, str]],
    ) -> DeepSeekChatCompletionResult:
        try:
            from openai import (
                APIConnectionError,
                APIStatusError,
                APITimeoutError,
                OpenAI,
                OpenAIError,
            )
        except ImportError as exc:
            raise DeepSeekConfigurationError(
                "Python package `openai` is not installed. Please install project dependencies including `openai`."
            ) from exc

        client = OpenAI(
            api_key=self._resolve_api_key(),
            base_url=DEEPSEEK_BASE_URL,
            timeout=self._resolve_timeout_seconds(),
        )

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=False,
            )
        except APITimeoutError as exc:
            raise DeepSeekTimeoutError(
                "DeepSeek API request timed out."
            ) from exc
        except APIConnectionError as exc:
            raise DeepSeekInvocationError(
                "Unable to connect to the DeepSeek API."
            ) from exc
        except APIStatusError as exc:
            status_code = getattr(exc, "status_code", None)
            if status_code:
                raise DeepSeekInvocationError(
                    f"DeepSeek API request failed with status {status_code}."
                ) from exc
            raise DeepSeekInvocationError(
                "DeepSeek API request failed."
            ) from exc
        except OpenAIError as exc:
            raise DeepSeekInvocationError(
                "DeepSeek API request failed."
            ) from exc

        choices = getattr(response, "choices", None) or []
        if not choices:
            raise DeepSeekEmptyResponseError("DeepSeek returned no choices.")

        first_choice = choices[0]
        message = getattr(first_choice, "message", None)
        content = self._flatten_message_content(getattr(message, "content", None))
        if not content:
            raise DeepSeekEmptyResponseError(
                "DeepSeek returned an empty message content."
            )

        usage = None
        raw_usage = getattr(response, "usage", None)
        if raw_usage is not None:
            usage = {
                key: value
                for key, value in {
                    "prompt_tokens": getattr(raw_usage, "prompt_tokens", None),
                    "completion_tokens": getattr(raw_usage, "completion_tokens", None),
                    "total_tokens": getattr(raw_usage, "total_tokens", None),
                }.items()
                if value is not None
            }

        return DeepSeekChatCompletionResult(
            content=content,
            model=getattr(response, "model", None),
            response_id=getattr(response, "id", None),
            finish_reason=getattr(first_choice, "finish_reason", None),
            usage=usage or None,
        )
