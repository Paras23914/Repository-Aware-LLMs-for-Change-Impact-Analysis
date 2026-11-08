"""Tests for the candidate-list family (C0_CAND..C3_CAND) and the prompt-size guards."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from cia.analysis import (
    CandidateBudgets,
    build_candidate_contexts,
    build_contexts,
    select_candidates,
)
from cia.data import CIAError, PredictorInput, RepositorySnapshot, TaskRecord, predictor_input
from cia.guards import PromptTooLargeError, detect_truncation, preflight_prompt_check


def _git(root: Path, *args: str) -> str:
    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
    })
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True,
        encoding="utf-8", env=env, check=False,
    )
    if result.returncode:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


class GuardTests(unittest.TestCase):
    def test_measured_clipped_prompts_are_detected(self) -> None:
        # Measured on IVY-1028: C1-C3 all reported 16,386 prompt tokens.
        for chars in (184_617, 210_162, 234_793):
            self.assertIsNotNone(detect_truncation(chars, 16_386, 32_768))

    def test_measured_intact_prompts_are_accepted(self) -> None:
        self.assertIsNone(detect_truncation(88_402, 26_220, 32_768))  # full-tree C0
        self.assertIsNone(detect_truncation(7_217, 1_731, 32_768))    # C0_CONSTRAINED
        self.assertIsNone(detect_truncation(1_000, None, 32_768))     # unknown count

    def test_window_limit_is_detected(self) -> None:
        self.assertIsNotNone(detect_truncation(100_000, 32_760, 32_768))

    def test_preflight_rejects_overflow_and_accepts_known_good(self) -> None:
        preflight_prompt_check(88_402, 32_768, 2_048)  # the pilot's full-tree C0 fits
        with self.assertRaises(PromptTooLargeError):
            preflight_prompt_check(184_617, 32_768, 2_048)


class CandidateFamilyTests(unittest.TestCase):
    def _repo(self, root: Path) -> RepositorySnapshot:
        _git(root, "init", "-q")
        main = root / "src/main/java/app"
        main.mkdir(parents=True)
        for index in range(30):
            (main / f"Widget{index}.java").write_text(
                f"package app; public class Widget{index} {{ void render{index}() {{}} }}\n",
                encoding="utf-8",
            )
        (main / "Parser.java").write_text(
            "package app;\npublic class Parser { Widget1 w; void parseSnapshot() {} }\n",
            encoding="utf-8",
        )
        tests = root / "src/test/java/app"
        tests.mkdir(parents=True)
        for index in range(15):
            (tests / f"Widget{index}Test.java").write_text(
                f"package app; public class Widget{index}Test {{}}\n", encoding="utf-8"
            )
        (root / "CHANGES.txt").write_text("changelog\n", encoding="utf-8")
        (root / "build.xml").write_text("<project/>\n", encoding="utf-8")
        (root / "logo.png").write_bytes(b"\x89PNG")
        docs = root / "doc"
        docs.mkdir()
        for index in range(25):
            (docs / f"page{index}.html").write_text(f"<p>page {index}</p>\n", encoding="utf-8")
        _git(root, "add", "--all")
        _git(root, "commit", "-qm", "fixture")
        return RepositorySnapshot.at_commit(root, _git(root, "rev-parse", "HEAD"))

    def _task(self, view: RepositorySnapshot) -> PredictorInput:
        record = TaskRecord(
            task_id="synthetic-1", source_name="s", source_url="https://example.invalid/s",
            repository_url="https://example.invalid/r", issue_url="https://example.invalid/i",
            issue_text="Parser fails on snapshot input in parseSnapshot",
            issue_text_source="test", issue_created_at="2020-01-01T00:00:00+00:00",
            target_sha="a" * 40, parent_sha=view.commit_sha,
            changed_paths=("src/main/java/app/Parser.java",), selection_decision="test",
        )
        return predictor_input(record, view)

    def test_candidate_list_is_bounded_unique_and_mixed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cia-cand-", dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir) / "repo"
            root.mkdir()
            task = self._task(self._repo(root))
            budgets = CandidateBudgets(candidate_limit=40, reserved_tests=5, reserved_non_java=6)
            candidates, counts = select_candidates(task, budgets)
            self.assertEqual(len(candidates), 40)
            self.assertEqual(len(set(candidates)), 40)
            self.assertIn("CHANGES.txt", candidates)        # root-level documentation file
            self.assertIn("build.xml", candidates)          # root-level build file
            self.assertNotIn("logo.png", candidates)        # binary files are never candidates
            self.assertEqual(counts["test_java"], 5)
            self.assertEqual(counts["non_java"], 6)
            self.assertEqual(candidates[0], "src/main/java/app/Parser.java")  # best lexical match

    def test_four_conditions_are_cumulative_within_budget(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cia-cand-", dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir) / "repo"
            root.mkdir()
            task = self._task(self._repo(root))
            budgets = CandidateBudgets(candidate_limit=40, reserved_tests=5, reserved_non_java=6,
                                       max_prompt_chars=30_000)
            c0, c1, c2, c3 = build_candidate_contexts(task, budgets)
            self.assertEqual(
                [c.condition for c in (c0, c1, c2, c3)],
                ["C0_CAND", "C1_CAND", "C2_CAND", "C3_CAND"],
            )
            for context in (c0, c1, c2, c3):
                self.assertLessEqual(len(context.text), budgets.max_prompt_chars)
            self.assertNotIn("## Seed and retrieved source files", c0.text)
            self.assertIn("## Seed and retrieved source files", c1.text)
            self.assertNotIn("## Dependency information", c1.text)
            self.assertIn("## Dependency information", c2.text)
            self.assertNotIn("## Tests, documentation", c2.text)
            self.assertIn("## Tests, documentation", c3.text)
            # Items only grow as context is added.
            self.assertLessEqual(len(c0.items), len(c1.items))
            self.assertLessEqual(len(c1.items), len(c2.items))
            self.assertLessEqual(len(c2.items), len(c3.items))

    def test_no_label_or_future_content_is_used(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cia-cand-", dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir) / "repo"
            root.mkdir()
            task = self._task(self._repo(root))
            # Same issue and snapshot give identical candidates regardless of the labels.
            relabelled = PredictorInput(repository=task.repository, issue_text=task.issue_text)
            self.assertEqual(select_candidates(task)[0], select_candidates(relabelled)[0])

    def test_oversized_issue_text_is_rejected_not_silently_clipped(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cia-cand-", dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir) / "repo"
            root.mkdir()
            task = self._task(self._repo(root))
            tiny = CandidateBudgets(candidate_limit=40, reserved_tests=5, reserved_non_java=6,
                                    max_prompt_chars=2_000)
            with self.assertRaises(CIAError):
                build_candidate_contexts(task, tiny)

    def test_original_contexts_are_unchanged_by_the_refactor(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cia-cand-", dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir) / "repo"
            root.mkdir()
            task = self._task(self._repo(root))
            conditions = [c.condition for c in build_contexts(task)]
            self.assertEqual(conditions, ["C0", "C1", "C2", "C3"])


if __name__ == "__main__":
    unittest.main()
