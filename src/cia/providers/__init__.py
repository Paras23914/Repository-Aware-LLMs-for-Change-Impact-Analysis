"""Model provider contracts and offline mock implementations."""

from cia.providers.base import CompletionRequest, CompletionResponse, ModelProvider
from cia.providers.mock import MockProvider
from cia.providers.openai_compatible import OpenAICompatibleConfig, OpenAICompatibleProvider
from cia.providers.ollama import OllamaConfig, OllamaProvider

__all__ = [
    "CompletionRequest", "CompletionResponse", "ModelProvider", "MockProvider",
    "OpenAICompatibleConfig", "OpenAICompatibleProvider",
    "OllamaConfig", "OllamaProvider",
]

