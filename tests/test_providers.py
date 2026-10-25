"""Consolidated tests for test_providers."""

from __future__ import annotations
import json
import unittest
import io
import os
import subprocess
import tempfile
from unittest.mock import patch
from cia.analysis import ContextDocument, build_c0
from cia.providers import CompletionRequest, OllamaConfig, OllamaProvider, OpenAICompatibleConfig, OpenAICompatibleProvider, MockProvider
from cia.prediction import run_prediction
from pathlib import Path
from cia.data import PredictionError, RepositorySnapshot, TaskRecord, predictor_input

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
    @patch("cia.providers.urlopen")
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
            with self.subTest(output=bad_output), patch("cia.providers.urlopen") as fake_urlopen:
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

    @patch("cia.providers.urlopen")
    def test_missing_model_and_timeout_report_clear_errors(self, fake_urlopen: object) -> None:
        fake_urlopen.return_value = FakeHTTPResponse({"models": [{"name": "other-model"}]})  # type: ignore[attr-defined]
        with self.assertRaisesRegex(RuntimeError, "not installed: qwen2.5-coder:7b"):
            OllamaProvider().complete(CompletionRequest("C0", "small prompt"))
        fake_urlopen.side_effect = TimeoutError("local request timed out")  # type: ignore[attr-defined]
        with self.assertRaisesRegex(RuntimeError, "Ollama request failed"):
            OllamaProvider().complete(CompletionRequest("C0", "small prompt"))

class OpenAICompatibleTests(unittest.TestCase):
    @patch("cia.providers.urlopen")
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

class MockProviderTests(unittest.TestCase):
    def git(self, root: Path, *args: str) -> str:
        env = os.environ.copy()
        env.update({
            "GIT_AUTHOR_NAME": "CIA provider test",
            "GIT_AUTHOR_EMAIL": "cia-test@example.invalid",
            "GIT_COMMITTER_NAME": "CIA provider test",
            "GIT_COMMITTER_EMAIL": "cia-test@example.invalid",
            "GIT_AUTHOR_DATE": "2020-01-01T00:00:00Z",
            "GIT_COMMITTER_DATE": "2020-01-01T00:00:00Z",
        })
        result = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True,
            encoding="utf-8", env=env, check=False,
        )
        if result.returncode:
            self.fail(f"git {' '.join(args)} failed: {result.stderr}")
        return result.stdout.strip()

    def test_mock_provider_produces_valid_logged_prediction_without_credentials(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cia-provider-", dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir) / "repo"
            root.mkdir()
            self.git(root, "init", "-q")
            java = root / "src/main/java/Example.java"
            java.parent.mkdir(parents=True)
            java.write_text("class Example {}\n", encoding="utf-8")
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "fixture")
            parent = self.git(root, "rev-parse", "HEAD")
            java.write_text("class Example { int x; }\n", encoding="utf-8")
            self.git(root, "add", "--all")
            self.git(root, "commit", "-m", "target")
            target = self.git(root, "rev-parse", "HEAD")
            record = TaskRecord.from_mapping({
                "task_id": "provider-synthetic-fixture",
                "source_name": "synthetic unittest fixture",
                "source_url": "https://example.invalid/source",
                "repository_url": "https://example.invalid/repository",
                "issue_url": "https://example.invalid/issue",
                "issue_text": "Update Example.",
                "issue_text_source": "inline synthetic test fixture",
                "issue_created_at": "2019-12-31T23:59:59Z",
                "target_sha": target,
                "parent_sha": parent,
                "changed_paths": ["src/main/java/Example.java"],
                "selection_decision": "synthetic test only",
            })
            view = RepositorySnapshot.at_commit(root, parent)
            task = predictor_input(record, view)
            context = build_c0(task)
            response = (
                '{"predictions":[{"path":"src/main/java/Example.java",'
                '"rationale":"The request names this Java component."}]}'
            )
            provider = MockProvider({"C0": response})
            result = run_prediction(record.task_id, context, provider)

            self.assertEqual(result.status, "ok")
            self.assertEqual(result.model_id, "mock/test")
            self.assertEqual(result.input_tokens, None)
            self.assertEqual(result.predictions[0].path, "src/main/java/Example.java")
            self.assertEqual(len(provider.requests), 1)
            self.assertEqual(provider.requests[0].condition, "C0")
            self.assertNotIn(target, provider.requests[0].prompt)
            self.assertIsNone(os.environ.get("CIA_CLOUD_API_KEY"))

            invalid_provider = MockProvider({"C0": '{"predictions":[{"path":"missing.java","rationale":"No."}]}'} )
            failed = run_prediction(record.task_id, context, invalid_provider)
            self.assertEqual(failed.status, "error")
            self.assertIn("not present at parent commit", failed.error or "")
            self.assertEqual(failed.predictions, ())
