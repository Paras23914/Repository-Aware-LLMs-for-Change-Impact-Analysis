"""Unit tests for the HTTP adapter with a mocked transport."""

from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch

from cia.providers import (
    CompletionRequest,
    OpenAICompatibleConfig,
    OpenAICompatibleProvider,
)


class FakeHTTPResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


class OpenAICompatibleTests(unittest.TestCase):
    @patch("cia.providers.openai_compatible.urlopen")
    def test_request_and_usage_parsing_without_network(self, fake_urlopen: object) -> None:
        fake_urlopen.return_value = FakeHTTPResponse({  # type: ignore[attr-defined]
            "model": "test-cloud-model",
            "choices": [{"message": {"content": '{"predictions":[]}'}}],
            "usage": {"prompt_tokens": 17, "completion_tokens": 4},
        })
        provider = OpenAICompatibleProvider(OpenAICompatibleConfig(
            base_url="https://provider.example.invalid/v1",
            model="configured-model",
            api_key=None,
        ))
        response = provider.complete(CompletionRequest("C0", "safe prompt"))
        call_args = fake_urlopen.call_args  # type: ignore[attr-defined]
        request = call_args.args[0]
        self.assertEqual(request.full_url, "https://provider.example.invalid/v1/chat/completions")
        self.assertNotIn("Authorization", request.headers)
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "configured-model")
        self.assertEqual(payload["messages"][0]["content"], "safe prompt")
        self.assertEqual(response.model_id, "test-cloud-model")
        self.assertEqual(response.input_tokens, 17)
        self.assertEqual(response.output_tokens, 4)


if __name__ == "__main__":
    unittest.main()

