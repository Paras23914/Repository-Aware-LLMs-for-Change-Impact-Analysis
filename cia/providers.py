"""Provider contract, test double, and local/cloud HTTP adapters."""

from __future__ import annotations
import ipaddress
import json
import os
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

@dataclass(frozen=True, slots=True)
class CompletionRequest:
    condition: str
    prompt: str
    temperature: float = 0.0
    max_output_tokens: int = 1024

@dataclass(frozen=True, slots=True)
class CompletionResponse:
    content: str
    model_id: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider_name: str | None = None
    model_digest: str | None = None
    generation_settings: dict[str, object] | None = None
    provider_metrics: dict[str, int | float] | None = None

class ModelProvider(Protocol):
    """Minimal provider contract; implementations receive prompt text only."""

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Return one completion or raise an exception with provider details."""

class MockProvider:
    """Return caller-supplied responses without network access or credentials."""

    def __init__(self, responses: dict[str, str], model_id: str = "mock/test") -> None:
        self._responses = dict(responses)
        self.model_id = model_id
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        self.requests.append(request)
        if request.condition not in self._responses:
            raise ValueError(f"mock has no response for condition {request.condition!r}")
        return CompletionResponse(
            content=self._responses[request.condition],
            model_id=self.model_id,
        )

def _json_request(url: str, *, method: str = "GET", payload: dict[str, object] | None = None,
                  timeout_seconds: float) -> dict[str, object]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(url, data=data, headers={"Content-Type": "application/json"}, method=method)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read(1000).decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama returned HTTP {exc.code}: {body}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"Ollama request failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Ollama returned invalid JSON") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Ollama response must be a JSON object")
    return result

@dataclass(frozen=True, slots=True)
class OllamaConfig:
    model_tag: str = "qwen2.5-coder:7b"
    base_url: str = "http://127.0.0.1:11434"
    timeout_seconds: float = 180.0
    num_ctx: int = 2048
    seed: int = 42
    top_p: float = 1.0
    top_k: int = 40
    repeat_penalty: float = 1.0
    response_format: str = "json"

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme != "http" or not parsed.hostname:
            raise ValueError("Ollama base_url must be an HTTP URL on a local interface")
        hostname = parsed.hostname.lower()
        is_loopback = hostname == "localhost"
        if not is_loopback:
            try:
                is_loopback = ipaddress.ip_address(hostname).is_loopback
            except ValueError:
                is_loopback = False
        if not is_loopback:
            raise ValueError("Ollama base_url must resolve to localhost or a loopback IP")
        if not self.model_tag.strip():
            raise ValueError("Ollama model_tag must not be empty")
        if self.timeout_seconds <= 0 or self.num_ctx <= 0:
            raise ValueError("Ollama timeout and context length must be positive")
        if self.top_k < 1 or not 0 < self.top_p <= 1 or self.repeat_penalty <= 0:
            raise ValueError("invalid Ollama sampling settings")
        if self.response_format not in {"json", "text"}:
            raise ValueError("Ollama response_format must be 'json' or 'text'")

class OllamaProvider:
    """Use Ollama's local ``/api/tags`` and ``/api/chat`` endpoints."""

    def __init__(self, config: OllamaConfig | None = None) -> None:
        self.config = config or OllamaConfig()

    def _model_metadata(self) -> dict[str, object]:
        result = _json_request(
            self.config.base_url.rstrip("/") + "/api/tags",
            timeout_seconds=self.config.timeout_seconds,
        )
        models = result.get("models")
        if not isinstance(models, list):
            raise RuntimeError("Ollama /api/tags response is missing its models array")
        for model in models:
            if isinstance(model, dict) and model.get("name") == self.config.model_tag:
                return model
        raise RuntimeError(f"configured Ollama model is not installed: {self.config.model_tag}")

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        if request.max_output_tokens < 1:
            raise ValueError("max_output_tokens must be positive")
        metadata = self._model_metadata()
        settings: dict[str, object] = {
            "temperature": request.temperature,
            "seed": self.config.seed,
            "top_p": self.config.top_p,
            "top_k": self.config.top_k,
            "repeat_penalty": self.config.repeat_penalty,
            "num_ctx": self.config.num_ctx,
            "num_predict": request.max_output_tokens,
            "format": self.config.response_format,
            "stream": False,
        }
        result = _json_request(
            self.config.base_url.rstrip("/") + "/api/chat",
            method="POST",
            payload={
                "model": self.config.model_tag,
                "messages": [{"role": "user", "content": request.prompt}],
                "stream": False,
                "format": self.config.response_format,
                "options": {
                    "temperature": settings["temperature"],
                    "seed": settings["seed"],
                    "top_p": settings["top_p"],
                    "top_k": settings["top_k"],
                    "repeat_penalty": settings["repeat_penalty"],
                    "num_ctx": settings["num_ctx"],
                    "num_predict": settings["num_predict"],
                },
            },
            timeout_seconds=self.config.timeout_seconds,
        )
        message = result.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise RuntimeError("Ollama /api/chat response is missing message.content")

        def optional_int(field: str) -> int | None:
            value = result.get(field)
            return value if isinstance(value, int) else None

        provider_metrics: dict[str, int | float] = {}
        for field in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration"):
            value = result.get(field)
            if isinstance(value, int):
                provider_metrics[f"{field}_ns"] = value
        model_id = result.get("model")
        return CompletionResponse(
            content=content,
            model_id=model_id if isinstance(model_id, str) else self.config.model_tag,
            input_tokens=optional_int("prompt_eval_count"),
            output_tokens=optional_int("eval_count"),
            provider_name="ollama",
            model_digest=metadata.get("digest") if isinstance(metadata.get("digest"), str) else None,
            generation_settings=settings,
            provider_metrics=provider_metrics,
        )

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
