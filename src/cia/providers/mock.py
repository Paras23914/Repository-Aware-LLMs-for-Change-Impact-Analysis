"""Deterministic in-process provider for tests and demonstrations."""

from __future__ import annotations

from cia.providers.base import CompletionRequest, CompletionResponse


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

