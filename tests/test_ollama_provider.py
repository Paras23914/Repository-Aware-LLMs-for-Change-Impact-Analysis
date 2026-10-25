"""Ollama adapter and shared ranked-path runner tests with mocked HTTP."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from cia.context import ContextDocument
from cia.providers import CompletionRequest, OllamaConfig, OllamaProvider
from cia.runner import run_prediction


class FakeHTTPResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


class StubRepository:
    commit_sha = "a" * 40

    def list_files(self) -> tuple[str, ...]:
        return ("src/main/java/example/QuoteCalculator.java",)


def tags() -> dict[str, object]:
    return {"models": [{
        "name": "qwen2.5-coder:7b",
        "digest": "dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364",
        "size": 4683087561,
    }]}


class OllamaProviderTests(unittest.TestCase):
    @patch("cia.providers.ollama.urlopen")
    def test_native_chat_response_flows_through_ranked_path_validator(self, fake_urlopen: object) -> None:
        fake_urlopen.side_effect = [  # type: ignore[attr-defined]
            FakeHTTPResponse(tags()),
            FakeHTTPResponse({
                "model": "qwen2.5-coder:7b",
                "message": {"role": "assistant", "content": json.dumps({
                    "predictions": [{
                        "path": "src/main/java/example/QuoteCalculator.java",
                        "rationale": "The request concerns the quote total calculation.",
                    }],
                })},
                "prompt_eval_count": 57,
                "eval_count": 18,
                "total_duration": 1200000000,
                "load_duration": 300000000,
                "prompt_eval_duration": 200000000,
                "eval_duration": 700000000,
            }),
        ]
        config = OllamaConfig()
        provider = OllamaProvider(config)
        context = ContextDocument(
            "C0", "synthetic prompt", StubRepository.commit_sha, (), StubRepository()  # type: ignore[arg-type]
        )
        result = run_prediction(
            "synthetic-ollama-provider-test", context, provider,
            temperature=0.0, max_output_tokens=128, run_kind="test-only",
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.provider_name, "ollama")
        self.assertEqual(result.model_id, "qwen2.5-coder:7b")
        self.assertEqual(result.model_digest, tags()["models"][0]["digest"])  # type: ignore[index]
        self.assertEqual(result.condition, "C0")
        self.assertEqual(result.input_tokens, 57)
        self.assertEqual(result.output_tokens, 18)
        self.assertEqual(result.predictions[0].path, "src/main/java/example/QuoteCalculator.java")
        self.assertEqual(result.provider_metrics["total_duration_ns"], 1200000000)
        self.assertEqual(result.generation_settings["seed"], 42)
        self.assertEqual(result.run_kind, "test-only")
        self.assertTrue(result.run_started_at.endswith("Z"))

        get_request = fake_urlopen.call_args_list[0].args[0]  # type: ignore[attr-defined]
        post_request = fake_urlopen.call_args_list[1].args[0]  # type: ignore[attr-defined]
        self.assertEqual(get_request.full_url, "http://127.0.0.1:11434/api/tags")
        self.assertEqual(post_request.full_url, "http://127.0.0.1:11434/api/chat")
        payload = json.loads(post_request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "qwen2.5-coder:7b")
        self.assertEqual(payload["format"], "json")
        self.assertEqual(payload["options"]["num_predict"], 128)
        self.assertEqual(payload["options"]["seed"], 42)

    def test_malformed_json_and_unknown_paths_are_logged_as_errors(self) -> None:
        context = ContextDocument(
            "C0", "synthetic prompt", StubRepository.commit_sha, (), StubRepository()  # type: ignore[arg-type]
        )
        bad_outputs = (
            "not-json",
            json.dumps({"predictions": [{"path": "src/NotTracked.java", "rationale": "test"}]}),
        )
        for bad_output in bad_outputs:
            with self.subTest(output=bad_output), patch("cia.providers.ollama.urlopen") as fake_urlopen:
                fake_urlopen.side_effect = [
                    FakeHTTPResponse(tags()),
                    FakeHTTPResponse({
                        "model": "qwen2.5-coder:7b",
                        "message": {"role": "assistant", "content": bad_output},
                    }),
                ]
                result = run_prediction(
                    "synthetic-ollama-invalid-output", context, OllamaProvider(), run_kind="test-only"
                )
                self.assertEqual(result.status, "error")
                self.assertIsNotNone(result.error)
                self.assertEqual(result.predictions, ())

    @patch("cia.providers.ollama.urlopen")
    def test_missing_model_and_timeout_report_clear_errors(self, fake_urlopen: object) -> None:
        fake_urlopen.return_value = FakeHTTPResponse({"models": [{"name": "other-model"}]})  # type: ignore[attr-defined]
        with self.assertRaisesRegex(RuntimeError, "not installed: qwen2.5-coder:7b"):
            OllamaProvider().complete(CompletionRequest("C0", "small prompt"))
        fake_urlopen.side_effect = TimeoutError("local request timed out")  # type: ignore[attr-defined]
        with self.assertRaisesRegex(RuntimeError, "Ollama request failed"):
            OllamaProvider().complete(CompletionRequest("C0", "small prompt"))


if __name__ == "__main__":
    unittest.main()

