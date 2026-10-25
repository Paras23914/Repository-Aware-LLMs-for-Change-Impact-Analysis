"""Repository snapshot handling of legacy Java source encodings."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from cia.repository import RepositorySnapshot


class RepositoryEncodingTests(unittest.TestCase):
    def test_decodes_legacy_latin1_text_deterministically(self) -> None:
        snapshot = RepositorySnapshot(Path("."), "a" * 40)

        def fake_git(_root: Path, *args: str) -> bytes:
            if args[:2] == ("ls-tree", "-r"):
                return b"src/Example.java\0"
            if args[0] == "show":
                return b"class Example { // caf\xe9\n}\n"
            raise AssertionError(f"unexpected Git command: {args!r}")

        with patch("cia.repository._git", side_effect=fake_git):
            self.assertIn("café", snapshot.read_file("src/Example.java"))


if __name__ == "__main__":
    unittest.main()
