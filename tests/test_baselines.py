"""Tests for dependency and parent-bounded co-change rankings."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from cia.baselines import DependencyIndex, historical_cochange_rank
from cia.repository import RepositorySnapshot


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
            self.assertNotIn(target_sha, view.history_commits())
            self.assertNotIn("src/main/java/example/TargetOnly.java", ranked)
            self.assertNotIn("src/main/java/example/FutureOnly.java", ranked)


if __name__ == "__main__":
    unittest.main()

