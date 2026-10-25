"""Deterministic C0-C3 context construction and manifest persistence."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from cia.baselines import DependencyIndex, historical_cochange_counts
from cia.errors import CIAError
from cia.repository import RepositorySnapshot
from cia.tasks import PredictorInput


@dataclass(frozen=True, slots=True)
class ContextItem:
    kind: str
    path: str | None
    reason: str
    source_commit: str
    content_sha256: str | None = None
    char_count: int = 0


@dataclass(frozen=True, slots=True)
class ContextDocument:
    condition: str
    text: str
    commit_sha: str
    items: tuple[ContextItem, ...]
    repository: RepositorySnapshot


@dataclass(frozen=True, slots=True)
class ContextBudgets:
    source_chars: int = 96_000
    dependency_chars: int = 24_000
    supplementary_chars: int = 24_000
    retrieved_source_limit: int = 5

    def __post_init__(self) -> None:
        if min(self.source_chars, self.dependency_chars, self.supplementary_chars) < 1:
            raise ValueError("context character budgets must be positive")
        if self.retrieved_source_limit < 0:
            raise ValueError("retrieved_source_limit must not be negative")


_TOKEN_RE = re.compile(r"[A-Za-z_$][\w$]*")
_TYPE_RE = re.compile(r"\b(?:class|interface|enum|record)\s+([A-Za-z_$][\w$]*)")
_PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)
_SIGNATURE_RE = re.compile(
    r"^\s*(?:package\s+|import\s+|(?:public|protected|private|abstract|final|static|default|native|synchronized|strictfp|sealed|non-sealed|class|interface|enum|record)\b).*(?:;|\{|\))?\s*$"
)


def _item(kind: str, path: str | None, reason: str, commit: str, text: str | None = None) -> ContextItem:
    return ContextItem(
        kind=kind,
        path=path,
        reason=reason,
        source_commit=commit,
        content_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest() if text is not None else None,
        char_count=len(text) if text is not None else 0,
    )


def _score_file(query_tokens: Counter[str], path: str, source: str) -> int:
    file_tokens = Counter(_TOKEN_RE.findall(path.lower() + " " + source.lower()))
    return sum(query_tokens[token] * file_tokens[token] for token in query_tokens)


def _source_paths(repository: RepositorySnapshot) -> tuple[str, ...]:
    return tuple(
        path for path in repository.list_files()
        if path.endswith(".java") and not path.endswith("package-info.java")
        and "/test/" not in f"/{path.lower()}/" and not path.lower().startswith("test/")
    )


def _rank_sources(query: str, repository: RepositorySnapshot) -> tuple[str, ...]:
    query_tokens = Counter(token.lower() for token in _TOKEN_RE.findall(query) if len(token) > 2)
    scored: list[tuple[int, str]] = []
    for path in _source_paths(repository):
        source = repository.read_file(path)
        scored.append((_score_file(query_tokens, path, source), path))
    # A zero-overlap tie is stable and explicit; it does not inspect target data.
    return tuple(path for _, path in sorted(scored, key=lambda item: (-item[0], item[1])))


def _truncate(text: str, remaining: int) -> str:
    if len(text) <= remaining:
        return text
    return text[:remaining]


def _class_names(repository: RepositorySnapshot, paths: tuple[str, ...]) -> set[str]:
    names: set[str] = set()
    for path in paths:
        names.update(_TYPE_RE.findall(repository.read_file(path)))
    return names


def _signature(source: str) -> str:
    selected = [line.rstrip() for line in source.splitlines() if _SIGNATURE_RE.match(line)]
    return "\n".join(selected)


def _base_context(predictor_task: PredictorInput) -> tuple[str, tuple[ContextItem, ...]]:
    repository = predictor_task.repository
    paths = repository.list_files()
    tree = "\n".join(paths)
    text = (
        "You are analyzing likely file impact for a software maintenance request.\n"
        "Return only a JSON object with a 'predictions' array containing up to 10 "
        "objects of the form {\"path\": string, \"rationale\": string}, most likely first.\n"
        "Use exact file paths from the supplied pre-change repository tree. Do not invent paths.\n\n"
        "## Change request\n"
        + predictor_task.issue_text
        + "\n\n## Repository file tree (pre-change)\n"
        + tree
        + "\n"
    )
    items = (
        _item("issue", None, "request supplied for analysis", repository.commit_sha, predictor_task.issue_text),
        *(
            _item("file_tree_path", path, "tracked at the fixed parent commit", repository.commit_sha)
            for path in paths
        ),
    )
    return text, items


def build_c0(predictor_task: PredictorInput) -> ContextDocument:
    """Build C0 from the request and pre-change file tree only."""
    text, items = _base_context(predictor_task)
    return ContextDocument("C0", text, predictor_task.repository.commit_sha, items, predictor_task.repository)


def build_contexts(
    predictor_task: PredictorInput, budgets: ContextBudgets | None = None
) -> tuple[ContextDocument, ContextDocument, ContextDocument, ContextDocument]:
    """Build all cumulative contexts from one immutable pre-change snapshot."""
    budgets = budgets or ContextBudgets()
    repository = predictor_task.repository
    base_text, base_items = _base_context(predictor_task)
    source_rank = _rank_sources(predictor_task.issue_text, repository)
    if not source_rank:
        raise CIAError("cannot construct C1: no production Java source files exist at the parent commit")
    seed = source_rank[0]

    c1_text = base_text + "\n## Seed and retrieved source files\n"
    c1_items = list(base_items)
    selected_sources: list[str] = []
    remaining = budgets.source_chars
    ordered = (seed, *(path for path in source_rank[1:] if path != seed))
    for index, path in enumerate(ordered):
        if index > budgets.retrieved_source_limit:
            break
        if remaining <= 0:
            break
        source = _truncate(repository.read_file(path), remaining)
        selected_sources.append(path)
        kind = "seed_source" if path == seed else "retrieved_source"
        label = "SEED" if path == seed else "RETRIEVED"
        c1_text += f"\n### {label}: {path}\n```java\n{source}\n```\n"
        c1_items.append(_item(kind, path, "lexically ranked from request against parent-revision source", repository.commit_sha, source))
        remaining -= len(source)
    c1_items_tuple = tuple(c1_items)
    c1 = ContextDocument("C1", c1_text, repository.commit_sha, c1_items_tuple, repository)

    dep_index = DependencyIndex.build(repository)
    dep_candidates: list[str] = []
    for path in selected_sources:
        for neighbor in dep_index.neighbors(path):
            if neighbor not in selected_sources and neighbor not in dep_candidates:
                dep_candidates.append(neighbor)
    c2_text = c1_text + "\n## Dependency information (parent revision)\n"
    c2_items = list(c1_items_tuple)
    remaining = budgets.dependency_chars
    for path in dep_candidates:
        if remaining <= 0:
            break
        signature = _truncate(_signature(repository.read_file(path)), remaining)
        if not signature:
            continue
        c2_text += f"\n### Dependency signatures: {path}\n```java\n{signature}\n```\n"
        c2_items.append(_item(
            "dependency_signature", path,
            "direct import/type reference to or from a C1 source file", repository.commit_sha, signature,
        ))
        remaining -= len(signature)
    c2_items_tuple = tuple(c2_items)
    c2 = ContextDocument("C2", c2_text, repository.commit_sha, c2_items_tuple, repository)

    c3_text = c2_text + "\n## Tests, documentation, and prior co-change (parent history only)\n"
    c3_items = list(c2_items_tuple)
    remaining = budgets.supplementary_chars
    type_names = _class_names(repository, tuple(selected_sources))
    java_paths = repository.list_files()
    tests: list[str] = []
    for path in java_paths:
        lower = f"/{path.lower()}/"
        is_test_path = "/test/" in lower or lower.startswith("/test/")
        if not is_test_path or not path.endswith(".java"):
            continue
        test_types = _TYPE_RE.findall(repository.read_file(path))
        if any(
            name in type_names or name.removesuffix("Test") in type_names
            or name.removeprefix("Test") in type_names
            for name in test_types
        ):
            tests.append(path)

    docs: list[str] = []
    seed_package_match = _PACKAGE_RE.search(repository.read_file(seed))
    seed_package = seed_package_match.group(1) if seed_package_match else ""
    for path in java_paths:
        if path.endswith("package-info.java"):
            package_match = _PACKAGE_RE.search(repository.read_file(path))
            if package_match and package_match.group(1) == seed_package:
                docs.append(path)
    query_tokens = set(token.lower() for token in _TOKEN_RE.findall(predictor_task.issue_text) if len(token) > 3)
    for path in java_paths:
        low = path.lower()
        if low.endswith((".md", ".rst", ".txt")) or "/docs/" in f"/{low}/":
            if path not in docs and any(token in low for token in query_tokens):
                docs.append(path)

    for path in sorted(set(tests)) + sorted(set(docs)):
        if remaining <= 0:
            break
        content = _truncate(repository.read_file(path), remaining)
        if not content:
            continue
        kind = "relevant_test" if path in tests else "relevant_documentation"
        heading = "Relevant test" if kind == "relevant_test" else "Relevant documentation"
        c3_text += f"\n### {heading}: {path}\n```\n{content}\n```\n"
        c3_items.append(_item(kind, path, "associated by declared type or package/issue terms", repository.commit_sha, content))
        remaining -= len(content)

    cochange = historical_cochange_counts(repository, seed)
    history_lines: list[str] = []
    for path in sorted(cochange, key=lambda candidate: (-cochange[candidate], candidate)):
        fact = f"{path}: co-changed with seed in {cochange[path]} prior non-merge commit(s)"
        if len(fact) > remaining:
            continue
        history_lines.append(fact)
        c3_items.append(_item(
            "historical_cochange", path,
            f"co-changed with seed in {cochange[path]} non-merge commits reachable from parent",
            repository.commit_sha, fact,
        ))
        remaining -= len(fact)
    if history_lines:
        c3_text += "\n### Prior co-change counts\n" + "\n".join(history_lines) + "\n"

    c3 = ContextDocument("C3", c3_text, repository.commit_sha, tuple(c3_items), repository)
    return (build_c0(predictor_task), c1, c2, c3)


def save_contexts(
    output_dir: str | Path,
    task_id: str,
    contexts: tuple[ContextDocument, ContextDocument, ContextDocument, ContextDocument],
) -> Path:
    """Write prompt text and content-hash manifests for an actual task run."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,100}", task_id):
        raise ValueError("task_id contains characters unsafe for an artifact filename")
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    manifest_rows: list[dict[str, object]] = []
    for context in contexts:
        prompt_path = directory / f"{task_id}_{context.condition}.txt"
        prompt_path.write_text(context.text, encoding="utf-8")
        manifest_rows.append({
            "task_id": task_id,
            "condition": context.condition,
            "source_commit": context.commit_sha,
            "prompt_file": prompt_path.name,
            "prompt_sha256": hashlib.sha256(context.text.encode("utf-8")).hexdigest(),
            "prompt_char_count": len(context.text),
            "items": [asdict(item) for item in context.items],
        })
    manifest_path = directory / f"{task_id}_context_manifest.json"
    manifest_path.write_text(json.dumps(manifest_rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest_path

