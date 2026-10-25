"""Consolidated tests for test_analysis."""

from __future__ import annotations
import os
import subprocess
import tempfile
import unittest
import json
from pathlib import Path
from cia.analysis import DependencyIndex, historical_cochange_rank, ContextBudgets, build_contexts, save_contexts, build_c0
from cia.data import RepositorySnapshot, TaskRecord, predictor_input, PredictionError
from cia.prediction import evaluate, validate_ranked_paths

class BaselineTests(unittest.TestCase):
    def git(self, root: Path, *args: str) -> str:
        env = os.environ.copy()
        env.update({
            "GIT_AUTHOR_NAME": "CIA baseline test",
            "GIT_AUTHOR_EMAIL": "cia-test@example.invalid",
            "GIT_COMMITTER_NAME": "CIA baseline test",
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

    def test_dependency_rank_finds_local_importers_deterministically(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cia-dep-", dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir) / "repo"
            root.mkdir()
            self.git(root, "init", "-q")
            base = root / "src/main/java/example"
            base.mkdir(parents=True)
            (base / "Service.java").write_text("package example; class Service {}\n", encoding="utf-8")
            (base / "App.java").write_text(
                "package example; import example.Service; class App { Service service; }\n",
                encoding="utf-8",
            )
            (base / "Consumer.java").write_text(
                "package example; class Consumer { App app; }\n", encoding="utf-8"
            )
            (base / "Unrelated.java").write_text(
                "package example; class Unrelated {}\n", encoding="utf-8"
            )
            self.commit(root, "fixture")
            view = RepositorySnapshot.at_commit(root, self.git(root, "rev-parse", "HEAD"))
            index = DependencyIndex.build(view)
            expected = (
                "src/main/java/example/Service.java",
                "src/main/java/example/App.java",
                "src/main/java/example/Consumer.java",
            )
            self.assertEqual(index.rank_from_seed(expected[0], view), expected)
            self.assertEqual(index.rank_from_seed(expected[0], view), expected)

    def test_cochange_uses_only_history_reachable_from_parent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cia-history-", dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir) / "repo"
            root.mkdir()
            self.git(root, "init", "-q")
            base = root / "src/main/java/example"
            base.mkdir(parents=True)
            files = {
                "Seed.java": "package example; class Seed {}\n",
                "Prior.java": "package example; class Prior {}\n",
                "TargetOnly.java": "package example; class TargetOnly {}\n",
                "FutureOnly.java": "package example; class FutureOnly {}\n",
            }
            for name, content in files.items():
                (base / name).write_text(content, encoding="utf-8")
            self.commit(root, "initial")

            (base / "Seed.java").write_text("package example; class Seed { int x; }\n", encoding="utf-8")
            (base / "Prior.java").write_text("package example; class Prior { int x; }\n", encoding="utf-8")
            parent_sha = self.commit(root, "historical co-change")

            (base / "Seed.java").write_text("package example; class Seed { int y; }\n", encoding="utf-8")
            (base / "TargetOnly.java").write_text("package example; class TargetOnly { int y; }\n", encoding="utf-8")
            target_sha = self.commit(root, "target future change")

            (base / "Seed.java").write_text("package example; class Seed { int z; }\n", encoding="utf-8")
            (base / "FutureOnly.java").write_text("package example; class FutureOnly { int z; }\n", encoding="utf-8")
            self.commit(root, "descendant future co-change")

            view = RepositorySnapshot.at_commit(root, parent_sha)
            ranked = historical_cochange_rank(view, "src/main/java/example/Seed.java")
            self.assertEqual(ranked, (
                "src/main/java/example/Seed.java",
                "src/main/java/example/Prior.java",
            ))
            self.assertNotIn(target_sha, tuple(commit for commit, _paths in view.history_changes()))
            self.assertNotIn("src/main/java/example/TargetOnly.java", ranked)
            self.assertNotIn("src/main/java/example/FutureOnly.java", ranked)

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
