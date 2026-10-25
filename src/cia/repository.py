"""Read-only access to a Git repository at an exact commit."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from cia.errors import RepositoryError
from cia.tasks import validate_repo_path


def _git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        details = result.stderr.decode("utf-8", errors="replace").strip()
        raise RepositoryError(f"git {' '.join(args)} failed: {details}")
    return result.stdout


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    """Immutable view of tracked repository files at one commit."""

    root: Path
    commit_sha: str

    @classmethod
    def at_commit(cls, root: str | Path, commit_sha: str) -> "RepositorySnapshot":
        repo_root = Path(root).resolve()
        if not repo_root.is_dir():
            raise RepositoryError(f"repository directory does not exist: {repo_root}")
        resolved = _git(repo_root, "rev-parse", "--verify", f"{commit_sha}^{{commit}}")
        actual = resolved.decode("ascii", errors="strict").strip().lower()
        if actual != commit_sha.lower():
            raise RepositoryError(f"Git resolved {commit_sha!r} to unexpected commit {actual!r}")
        return cls(root=repo_root, commit_sha=actual)

    @lru_cache(maxsize=128)
    def list_files(self) -> tuple[str, ...]:
        output = _git(self.root, "ls-tree", "-r", "--name-only", "-z", self.commit_sha)
        paths = [part.decode("utf-8", errors="surrogateescape") for part in output.split(b"\0") if part]
        return tuple(sorted(paths))

    def read_file(self, path: str) -> str:
        safe_path = validate_repo_path(path)
        if safe_path not in set(self.list_files()):
            raise RepositoryError(f"path is not a tracked file at {self.commit_sha}: {safe_path}")
        output = _git(self.root, "show", f"{self.commit_sha}:{safe_path}")
        try:
            return output.decode("utf-8")
        except UnicodeDecodeError:
            # Older Java repositories commonly contain ISO-8859-1 source or
            # test fixtures. Latin-1 is a deterministic byte-preserving
            # fallback; ASCII syntax used by the analyzers remains intact.
            return output.decode("latin-1")

    def first_parent(self, commit_sha: str) -> str:
        output = _git(self.root, "rev-parse", "--verify", f"{commit_sha}^1")
        return output.decode("ascii", errors="strict").strip().lower()

    def changed_paths(self, parent_sha: str, target_sha: str) -> tuple[str, ...]:
        output = _git(self.root, "diff", "--name-only", "-z", parent_sha, target_sha, "--")
        paths = [part.decode("utf-8", errors="surrogateescape") for part in output.split(b"\0") if part]
        return tuple(sorted(paths))

    def history_commits(self, include_merges: bool = False) -> tuple[str, ...]:
        """Return commits reachable from this snapshot, newest first."""
        args = ["rev-list", "--topo-order"]
        if not include_merges:
            args.append("--no-merges")
        args.append(self.commit_sha)
        output = _git(self.root, *args)
        return tuple(line.decode("ascii") for line in output.splitlines() if line)

    @lru_cache(maxsize=32)
    def history_changes(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        """Read non-merge commit paths reachable from this snapshot in one Git call."""
        output = _git(
            self.root, "log", "--no-merges", "--topo-order", "--no-renames",
            "--format=format:%x1e%H %P%x1f", "--name-only", self.commit_sha,
        )
        result: list[tuple[str, tuple[str, ...]]] = []
        for chunk in output.decode("utf-8", errors="surrogateescape").split("\x1e"):
            if "\x1f" not in chunk:
                continue
            header, paths_text = chunk.split("\x1f", 1)
            fields = header.strip().split()
            if not fields or len(fields) == 1:
                # Ignore the root import: it has no preceding co-change interval.
                continue
            paths = tuple(sorted(path for path in paths_text.splitlines() if path))
            result.append((fields[0].lower(), paths))
        return tuple(result)

    def paths_changed_in_commit(self, commit_sha: str) -> tuple[str, ...]:
        """Read a commit's changed paths; callers must use history_commits()."""
        output = _git(
            self.root, "diff-tree", "--root", "--no-commit-id", "--name-only",
            "--no-renames", "-r", "-z", commit_sha,
        )
        paths = [part.decode("utf-8", errors="surrogateescape") for part in output.split(b"\0") if part]
        return tuple(sorted(paths))

    def commit_parents(self, commit_sha: str) -> tuple[str, ...]:
        """Return a commit's recorded parents, empty for a repository root."""
        output = _git(self.root, "rev-list", "--parents", "-n", "1", commit_sha)
        fields = output.decode("ascii").strip().split()
        return tuple(fields[1:])

    def validate_task_revision(
        self,
        target_sha: str,
        parent_sha: str,
        expected_paths: tuple[str, ...],
        issue_created_at: str,
    ) -> None:
        resolved_target = _git(self.root, "rev-parse", "--verify", f"{target_sha}^{{commit}}")
        resolved_parent = _git(self.root, "rev-parse", "--verify", f"{parent_sha}^{{commit}}")
        if resolved_target.decode("ascii").strip().lower() != target_sha.lower():
            raise RepositoryError("target SHA does not resolve to the requested commit")
        if resolved_parent.decode("ascii").strip().lower() != parent_sha.lower():
            raise RepositoryError("parent SHA does not resolve to the requested commit")
        actual_parent = self.first_parent(target_sha)
        if actual_parent != parent_sha.lower():
            raise RepositoryError(f"recorded parent is not target's first parent: {actual_parent}")
        try:
            issue_time = datetime.fromisoformat(issue_created_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise RepositoryError("issue creation time must be an ISO-8601 timestamp") from exc
        if issue_time.tzinfo is None:
            raise RepositoryError("issue creation time must include a timezone offset")
        target_time_raw = _git(self.root, "show", "-s", "--format=%cI", target_sha)
        target_time = datetime.fromisoformat(target_time_raw.decode("ascii").strip().replace("Z", "+00:00"))
        if issue_time >= target_time:
            raise RepositoryError("issue text was not demonstrably available before the target commit")
        actual_paths = self.changed_paths(parent_sha, target_sha)
        if tuple(sorted(expected_paths)) != actual_paths:
            raise RepositoryError(
                "manifest changed_paths do not match the Git diff; "
                f"manifest={sorted(expected_paths)!r}, git={list(actual_paths)!r}"
            )

