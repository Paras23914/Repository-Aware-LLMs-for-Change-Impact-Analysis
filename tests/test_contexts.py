"""Context ablation and manifest tests using an offline synthetic repository."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from cia.context import ContextBudgets, build_contexts, save_contexts
from cia.repository import RepositorySnapshot
from cia.tasks import TaskRecord, predictor_input


class ContextTests(unittest.TestCase):
    def git(self, root: Path, *args: str) -> str:
        env = os.environ.copy()
        env.update({
            "GIT_AUTHOR_NAME": "CIA context test",
            "GIT_AUTHOR_EMAIL": "cia-test@example.invalid",
            "GIT_COMMITTER_NAME": "CIA context test",
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

    def test_contexts_are_cumulative_and_add_only_allowed_prechange_inputs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cia-context-", dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir) / "repo"
            root.mkdir()
            self.git(root, "init", "-q")
            main = root / "src/main/java/example"
            test = root / "src/test/java/example"
            main.mkdir(parents=True)
            test.mkdir(parents=True)
            (main / "Service.java").write_text(
                "package example;\npublic class Service { int response() { return 1; } }\n",
                encoding="utf-8",
            )
            (main / "App.java").write_text(
                "package example;\nimport example.Service;\npublic class App { Service service; }\n",
                encoding="utf-8",
            )
            (main / "package-info.java").write_text(
                "/** Service package documentation. */\npackage example;\n", encoding="utf-8"
            )
            (test / "ServiceTest.java").write_text(
                "package example;\nclass ServiceTest { Service service; }\n", encoding="utf-8"
            )
            (root / "README.md").write_text("Service behavior documentation.\n", encoding="utf-8")
            self.commit(root, "initial files")

            (main / "Service.java").write_text(
                "package example;\npublic class Service { int response() { return 3; } }\n",
                encoding="utf-8",
            )
            (main / "App.java").write_text(
                "package example;\nimport example.Service;\npublic class App { Service service; int changed; }\n",
                encoding="utf-8",
            )
            parent_sha = self.commit(root, "historical service and app co-change")

            (main / "Service.java").write_text(
                "package example;\npublic class Service { int response() { return 4; } }\n"
                "// FUTURE_PATCH_SECRET\n",
                encoding="utf-8",
            )
            target_sha = self.commit(root, "future target patch")

            record = TaskRecord.from_mapping({
                "task_id": "context-synthetic-fixture",
                "source_name": "synthetic unittest fixture",
                "source_url": "https://example.invalid/synthetic-source",
                "repository_url": "https://example.invalid/synthetic-repo",
                "issue_url": "https://example.invalid/synthetic-issue",
                "issue_text": "Change the Service response return value.",
                "issue_text_source": "inline synthetic test fixture",
                "issue_created_at": "2019-12-31T23:59:59Z",
                "target_sha": target_sha,
                "parent_sha": parent_sha,
                "changed_paths": ["src/main/java/example/Service.java"],
                "selection_decision": "synthetic test only",
            })
            view = RepositorySnapshot.at_commit(root, parent_sha)
            view.validate_task_revision(target_sha, parent_sha, record.changed_paths, record.issue_created_at or "")
            task = predictor_input(record, view)
            contexts = build_contexts(
                task,
                ContextBudgets(source_chars=20_000, dependency_chars=20_000,
                               supplementary_chars=20_000, retrieved_source_limit=0),
            )
            c0, c1, c2, c3 = contexts
            self.assertEqual((c0.condition, c1.condition, c2.condition, c3.condition), ("C0", "C1", "C2", "C3"))
            self.assertEqual(c0.items[0].kind, "issue")
            self.assertTrue(all(item.kind == "file_tree_path" for item in c0.items[1:]))
            self.assertIn("src/main/java/example/Service.java", c0.text)
            self.assertNotIn("int response()", c0.text)

            self.assertEqual(c1.items[:len(c0.items)], c0.items)
            c1_added = c1.items[len(c0.items):]
            self.assertTrue(c1_added)
            self.assertTrue(all(item.kind in {"seed_source", "retrieved_source"} for item in c1_added))

            self.assertEqual(c2.items[:len(c1.items)], c1.items)
            c2_added = c2.items[len(c1.items):]
            self.assertTrue(c2_added)
            self.assertTrue(all(item.kind == "dependency_signature" for item in c2_added))
            self.assertIn("src/main/java/example/App.java", {item.path for item in c2_added})

            self.assertEqual(c3.items[:len(c2.items)], c2.items)
            c3_added = c3.items[len(c2.items):]
            allowed_c3 = {"relevant_test", "relevant_documentation", "historical_cochange"}
            self.assertTrue(c3_added)
            self.assertTrue(all(item.kind in allowed_c3 for item in c3_added))
            self.assertTrue(any(item.kind == "relevant_test" for item in c3_added))
            self.assertTrue(any(item.kind == "relevant_documentation" for item in c3_added))
            self.assertTrue(any(item.kind == "historical_cochange" for item in c3_added))

            for context in contexts:
                self.assertEqual(context.commit_sha, parent_sha)
                self.assertNotIn("FUTURE_PATCH_SECRET", context.text)
                self.assertNotIn(target_sha, context.text)

            output = Path(temp_dir) / "saved-contexts"
            manifest_path = save_contexts(output, record.task_id, contexts)
            saved = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual([row["condition"] for row in saved], ["C0", "C1", "C2", "C3"])
            self.assertTrue(all(row["source_commit"] == parent_sha for row in saved))
            self.assertTrue(all(len(row["prompt_sha256"]) == 64 for row in saved))


if __name__ == "__main__":
    unittest.main()

