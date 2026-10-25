"""Consolidated tests for test_data."""

from __future__ import annotations
import unittest
from cia.data import ManifestError, TaskRecord, RepositorySnapshot
from pathlib import Path
from unittest.mock import patch

class TaskManifestTests(unittest.TestCase):
    def row(self) -> dict[str, object]:
        return {
            "task_id": "synthetic-manifest-test",
            "source_name": "synthetic fixture",
            "source_url": "https://example.invalid/source",
            "repository_url": "https://example.invalid/repository",
            "issue_url": "https://example.invalid/issue",
            "issue_text": "Synthetic issue text.",
            "issue_text_source": "inline test fixture",
            "issue_created_at": "2019-12-31T23:59:59Z",
            "target_sha": "1" * 40,
            "parent_sha": "2" * 40,
            "changed_paths": ["src/main/java/Example.java"],
            "selection_decision": "synthetic test only",
        }

    def test_requires_timezone_aware_issue_timestamp(self) -> None:
        row = self.row()
        row["issue_created_at"] = "2019-12-31T23:59:59"
        with self.assertRaisesRegex(ManifestError, "timezone offset"):
            TaskRecord.from_mapping(row)

    def test_rejects_parent_traversal_in_gold_paths(self) -> None:
        row = self.row()
        row["changed_paths"] = ["../outside.java"]
        with self.assertRaisesRegex(ManifestError, "safe repository-relative"):
            TaskRecord.from_mapping(row)

class RepositoryEncodingTests(unittest.TestCase):
    def test_decodes_legacy_latin1_text_deterministically(self) -> None:
        snapshot = RepositorySnapshot(Path("."), "a" * 40)

        def fake_git(_root: Path, *args: str) -> bytes:
            if args[:2] == ("ls-tree", "-r"):
                return b"src/Example.java\0"
            if args[0] == "show":
                return b"class Example { // caf\xe9\n}\n"
            raise AssertionError(f"unexpected Git command: {args!r}")

        with patch("cia.data._git", side_effect=fake_git):
            self.assertIn("café", snapshot.read_file("src/Example.java"))
