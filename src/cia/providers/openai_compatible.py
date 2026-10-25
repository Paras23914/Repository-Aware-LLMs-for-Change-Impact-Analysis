"""OpenAI Chat Completions-compatible HTTP adapter using only stdlib."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from cia.providers.base import CompletionRequest, CompletionResponse


@dataclass(frozen=True, slots=True)
class OpenAICompatibleConfig:
    base_url: str
    model: str
    api_key: str | None = None
    timeout_seconds: float = 120.0

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("provider base_url must be an absolute HTTP(S) URL")
        if not self.model.strip():
            raise ValueError("provider model identifier must not be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("provider timeout_seconds must be positive")

    @classmethod
    def from_environment(
        cls,
        *,
        base_url_env: str,
        model_env: str,
        api_key_env: str,
        default_model: str | None = None,
        timeout_seconds: float = 120.0,
        require_api_key: bool = False,
    ) -> "OpenAICompatibleConfig":
        base_url = os.environ.get(base_url_env, "").strip()
        model = os.environ.get(model_env, default_model or "").strip()
        api_key = os.environ.get(api_key_env, "").strip() or None
        if not base_url:
            raise ValueError(f"set {base_url_env} to the compatible provider base URL")
        if not model:
            raise ValueError(f"set {model_env} to the provider's exact model identifier")
        if require_api_key and not api_key:
            raise ValueError(f"set {api_key_env} in the environment; do not put credentials in config files")
        return cls(base_url=base_url, model=model, api_key=api_key, timeout_seconds=timeout_seconds)


class OpenAICompatibleProvider:
    """Call a server that implements OpenAI-style ``/chat/completions``."""

    def __init__(self, config: OpenAICompatibleConfig) -> None:
        self.config = config

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        endpoint = self.config.base_url.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        payload = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": request.prompt}],
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
            "stream": False,
        }
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        http_request = Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(http_request, timeout=self.config.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            # Do not include request headers or configured credential values.
            body = exc.read(1000).decode("utf-8", errors="replace")
            raise RuntimeError(f"provider returned HTTP {exc.code}: {body}") from exc
        except (URLError, TimeoutError) as exc:
            raise RuntimeError(f"provider request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("provider response was not valid JSON") from exc

        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("provider response is missing choices[0].message.content") from exc
        if not isinstance(content, str):
            raise RuntimeError("provider message content must be a string")
        usage = result.get("usage") or {}
        input_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")
        model_id = result.get("model") or self.config.model
        return CompletionResponse(
            content=content,
            model_id=str(model_id),
            input_tokens=input_tokens if isinstance(input_tokens, int) else None,
            output_tokens=output_tokens if isinstance(output_tokens, int) else None,
            provider_name="openai-compatible",
            generation_settings={
                "temperature": request.temperature,
                "max_output_tokens": request.max_output_tokens,
                "stream": False,
            },
        )

