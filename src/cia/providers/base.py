"""Provider-independent request and response types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


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

