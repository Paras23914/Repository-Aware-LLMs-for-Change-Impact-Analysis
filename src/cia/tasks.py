"""Validated task manifest records and predictor-safe task inputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any, Mapping
from urllib.parse import urlparse

from cia.errors import ManifestError


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{field} must be a non-empty string")
    return value.strip()


def _require_url(value: Any, field: str) -> str:
    result = _require_text(value, field)
    parsed = urlparse(result)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ManifestError(f"{field} must be an absolute HTTP(S) URL")
    return result


def _require_sha(value: Any, field: str) -> str:
    result = _require_text(value, field).lower()
    if len(result) != 40 or any(ch not in "0123456789abcdef" for ch in result):
        raise ManifestError(f"{field} must be a full 40-character Git SHA-1")
    return result


def validate_repo_path(value: Any, field: str = "path") -> str:
    result = _require_text(value, field)
    path = PurePosixPath(result)
    if path.is_absolute() or ".." in path.parts or "\\" in result:
        raise ManifestError(f"{field} must be a safe repository-relative POSIX path")
    if result in {".", ""}:
        raise ManifestError(f"{field} must name a repository file")
    return result


@dataclass(frozen=True, slots=True)
class TaskRecord:
    """Gold-bearing manifest record; do not pass this object to predictors."""

    task_id: str
    source_name: str
    source_url: str
    repository_url: str
    issue_url: str
    issue_text: str
    issue_text_source: str
    target_sha: str
    parent_sha: str
    changed_paths: tuple[str, ...]
    selection_decision: str
    issue_created_at: str | None = None
    cleaning_decisions: tuple[str, ...] = ()
    suitability_notes: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "TaskRecord":
        if not isinstance(raw, Mapping):
            raise ManifestError("manifest row must be a JSON object")
        required = {
            "task_id", "source_name", "source_url", "repository_url", "issue_url",
            "issue_text", "issue_text_source", "issue_created_at", "target_sha", "parent_sha",
            "changed_paths", "selection_decision",
        }
        missing = sorted(required - raw.keys())
        extra = sorted(raw.keys() - (required | {
            "issue_created_at", "cleaning_decisions", "suitability_notes",
        }))
        if missing:
            raise ManifestError(f"manifest row is missing required fields: {', '.join(missing)}")
        if extra:
            raise ManifestError(f"manifest row has unsupported fields: {', '.join(extra)}")

        target_sha = _require_sha(raw["target_sha"], "target_sha")
        parent_sha = _require_sha(raw["parent_sha"], "parent_sha")
        if target_sha == parent_sha:
            raise ManifestError("target_sha and parent_sha must be different commits")

        paths = raw["changed_paths"]
        if not isinstance(paths, list) or not paths:
            raise ManifestError("changed_paths must be a non-empty JSON array")
        safe_paths = tuple(validate_repo_path(path, "changed_paths item") for path in paths)
        if len(set(safe_paths)) != len(safe_paths):
            raise ManifestError("changed_paths must not contain duplicates")

        created_at = raw.get("issue_created_at")
        created_at = _require_text(created_at, "issue_created_at")
        try:
            parsed_created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ManifestError("issue_created_at must be an ISO-8601 timestamp") from exc
        if parsed_created_at.tzinfo is None:
            raise ManifestError("issue_created_at must include a timezone offset")

        def text_array(field: str) -> tuple[str, ...]:
            value = raw.get(field, [])
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise ManifestError(f"{field} must be an array of strings")
            return tuple(value)

        return cls(
            task_id=_require_text(raw["task_id"], "task_id"),
            source_name=_require_text(raw["source_name"], "source_name"),
            source_url=_require_url(raw["source_url"], "source_url"),
            repository_url=_require_url(raw["repository_url"], "repository_url"),
            issue_url=_require_url(raw["issue_url"], "issue_url"),
            issue_text=_require_text(raw["issue_text"], "issue_text"),
            issue_text_source=_require_text(raw["issue_text_source"], "issue_text_source"),
            target_sha=target_sha,
            parent_sha=parent_sha,
            changed_paths=safe_paths,
            selection_decision=_require_text(raw["selection_decision"], "selection_decision"),
            issue_created_at=created_at,
            cleaning_decisions=text_array("cleaning_decisions"),
            suitability_notes=text_array("suitability_notes"),
        )


@dataclass(frozen=True, slots=True)
class PredictorInput:
    """Only request text and the pre-change repository view reach predictors."""

    issue_text: str
    repository: "RepositorySnapshot"


def load_manifest(path: str) -> list[TaskRecord]:
    """Read and validate JSONL task records; blank lines are ignored."""
    import json
    from pathlib import Path

    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise ManifestError(f"task manifest does not exist: {manifest_path}")
    records: list[TaskRecord] = []
    seen_ids: set[str] = set()
    with manifest_path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                record = TaskRecord.from_mapping(payload)
            except (json.JSONDecodeError, ManifestError) as exc:
                raise ManifestError(f"{manifest_path}:{line_number}: {exc}") from exc
            if record.task_id in seen_ids:
                raise ManifestError(f"{manifest_path}:{line_number}: duplicate task_id {record.task_id!r}")
            seen_ids.add(record.task_id)
            records.append(record)
    return records


def predictor_input(record: TaskRecord, repository: "RepositorySnapshot") -> PredictorInput:
    """Create a predictor payload without target SHA or reference paths."""
    if record.parent_sha != repository.commit_sha:
        raise ManifestError(
            f"repository snapshot is at {repository.commit_sha}, expected parent {record.parent_sha}"
        )
    return PredictorInput(issue_text=record.issue_text, repository=repository)


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cia.repository import RepositorySnapshot

