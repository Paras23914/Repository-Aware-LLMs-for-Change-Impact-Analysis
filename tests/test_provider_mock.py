"""Provider contract and runner tests that need no API keys."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from cia.context import build_c0
from cia.errors import PredictionError
from cia.providers import MockProvider
from cia.repository import RepositorySnapshot
from cia.runner import run_prediction
from cia.tasks import TaskRecord, predictor_input


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


if __name__ == "__main__":
    unittest.main()

