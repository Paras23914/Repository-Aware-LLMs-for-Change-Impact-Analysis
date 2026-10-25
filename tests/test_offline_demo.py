"""Offline end-to-end proof using a temporary, synthetic Java repository."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from cia.context import build_c0
from cia.errors import PredictionError
from cia.predictions import evaluate, validate_ranked_paths
from cia.repository import RepositorySnapshot
from cia.tasks import TaskRecord, predictor_input


class OfflineDemoTests(unittest.TestCase):
    def git(self, root: Path, *args: str) -> str:
        env = os.environ.copy()
        env.update({
            "GIT_AUTHOR_NAME": "CIA synthetic test",
            "GIT_AUTHOR_EMAIL": "cia-test@example.invalid",
            "GIT_COMMITTER_NAME": "CIA synthetic test",
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

    def commit(self, root: Path, message: str) -> str:
        self.git(root, "add", "--all")
        self.git(root, "commit", "-m", message)
        return self.git(root, "rev-parse", "HEAD")

    def test_synthetic_repository_to_metrics_without_network_or_model(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cia-offline-", dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir) / "repo"
            root.mkdir()
            self.git(root, "init", "-q")
            (root / "src/main/java/example/A.java").parent.mkdir(parents=True)
            (root / "src/main/java/example/A.java").write_text(
                "package example;\nclass A { B b; }\n", encoding="utf-8"
            )
            (root / "src/main/java/example/B.java").write_text(
                "package example;\nclass B { int value() { return 1; } }\n", encoding="utf-8"
            )
            parent_sha = self.commit(root, "synthetic parent")

            (root / "src/main/java/example/B.java").write_text(
                "package example;\nclass B { int value() { return 2; } }\n"
                "// TARGET_PATCH_SECRET\n", encoding="utf-8"
            )
            target_sha = self.commit(root, "synthetic target change")
            record = TaskRecord.from_mapping({
                "task_id": "synthetic-offline-fixture",
                "source_name": "synthetic unittest fixture",
                "source_url": "https://example.invalid/synthetic-source",
                "repository_url": "https://example.invalid/synthetic-repository",
                "issue_url": "https://example.invalid/synthetic-issue",
                "issue_text": "Change the value returned by B.",
                "issue_text_source": "inline synthetic test fixture",
                "issue_created_at": "2019-12-31T23:59:59Z",
                "target_sha": target_sha,
                "parent_sha": parent_sha,
                "changed_paths": ["src/main/java/example/B.java"],
                "selection_decision": "synthetic test only; not an empirical task",
            })

            repo_view = RepositorySnapshot.at_commit(root, record.parent_sha)
            repo_view.validate_task_revision(
                record.target_sha, record.parent_sha, record.changed_paths, record.issue_created_at or ""
            )
            self.assertEqual(
                repo_view.read_file("src/main/java/example/B.java"),
                "package example;\nclass B { int value() { return 1; } }\n",
            )

            predictor_task = predictor_input(record, repo_view)
            context = build_c0(predictor_task)
            self.assertEqual(context.condition, "C0")
            self.assertIn("Change the value returned by B.", context.text)
            self.assertIn("src/main/java/example/B.java", context.text)
            self.assertNotIn("TARGET_PATCH_SECRET", context.text)
            self.assertNotIn(target_sha, context.text)
            self.assertNotIn("changed_paths", repr(predictor_task))

            ranked = validate_ranked_paths(
                ["src/main/java/example/B.java", "src/main/java/example/A.java"], repo_view
            )
            score = evaluate(ranked, record.changed_paths)
            self.assertEqual(score.precision, 0.5)
            self.assertEqual(score.recall, 1.0)
            self.assertAlmostEqual(score.f1, 2 / 3)
            self.assertEqual(score.recall_at_5, 1.0)
            self.assertEqual(score.recall_at_10, 1.0)
            self.assertEqual(score.true_positives, 1)

            with self.assertRaisesRegex(PredictionError, "not present at parent commit"):
                validate_ranked_paths(["src/main/java/example/NewFile.java"], repo_view)


if __name__ == "__main__":
    unittest.main()

