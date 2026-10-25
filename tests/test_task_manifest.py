"""Manifest validation tests for traceability and safe repository paths."""

from __future__ import annotations

import unittest

from cia.errors import ManifestError
from cia.tasks import TaskRecord


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


if __name__ == "__main__":
    unittest.main()

