"""Java dependency/history analysis and C0-C3 context construction."""

from __future__ import annotations
import re
import hashlib
import json
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, asdict
from pathlib import Path
from cia.data import CIAError, PredictionError, PredictorInput, RepositorySnapshot, validate_repo_path

_PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)

_IMPORT_RE = re.compile(r"^\s*import\s+(?!static\b)([\w.*]+)\s*;", re.MULTILINE)

_TYPE_RE = re.compile(r"\b(?:class|interface|enum|record)\s+([A-Za-z_$][\w$]*)")

_STATIC_IMPORT_RE = re.compile(r"^\s*import\s+static\s+([\w.]+)\s*;", re.MULTILINE)

@dataclass(frozen=True, slots=True)
class DependencyIndex:
    """Approximate Java type-reference graph from a fixed repository snapshot."""

    # A -> B means source A refers to a type declared in B.
    dependents_by_dependency: dict[str, tuple[str, ...]]
    dependencies_by_source: dict[str, tuple[str, ...]]

    @classmethod
    def build(cls, repository: RepositorySnapshot) -> "DependencyIndex":
        java_paths = [p for p in repository.list_files() if p.endswith(".java")]
        sources = {path: repository.read_file(path) for path in java_paths}
        package_by_path: dict[str, str] = {}
        types_by_name: dict[str, list[str]] = defaultdict(list)
        for path, source in sources.items():
            package_match = _PACKAGE_RE.search(source)
            package = package_match.group(1) if package_match else ""
            package_by_path[path] = package
            names = set(_TYPE_RE.findall(source))
            for name in names:
                types_by_name[name].append(path)

        reverse: dict[str, set[str]] = defaultdict(set)
        forward: dict[str, set[str]] = defaultdict(set)
        for source_path, source in sources.items():
            package = package_by_path[source_path]
            imported_types: set[str] = set()
            for match in _IMPORT_RE.finditer(source):
                qualified = match.group(1)
                if qualified.endswith(".*"):
                    continue
                imported_types.add(qualified.rsplit(".", 1)[-1])
            for match in _STATIC_IMPORT_RE.finditer(source):
                imported_types.add(match.group(1).split(".")[-2])

            # Explicit imports are strong evidence. Same-package references are
            # resolved by Java type name; ambiguous duplicate names are skipped.
            target_paths: set[str] = set()
            for type_name in imported_types:
                matches = types_by_name.get(type_name, [])
                if len(matches) == 1:
                    target_paths.add(matches[0])
            for type_name, matches in types_by_name.items():
                if len(matches) != 1 or matches[0] == source_path:
                    continue
                target_path = matches[0]
                if package_by_path[target_path] == package and re.search(
                    rf"\b{re.escape(type_name)}\b", source
                ):
                    target_paths.add(target_path)
            for dependency_path in target_paths:
                reverse[dependency_path].add(source_path)
                forward[source_path].add(dependency_path)

        return cls(
            dependents_by_dependency={key: tuple(sorted(values)) for key, values in sorted(reverse.items())},
            dependencies_by_source={key: tuple(sorted(values)) for key, values in sorted(forward.items())},
        )

    def neighbors(self, path: str) -> tuple[str, ...]:
        """Return direct local Java references and reverse references."""
        return tuple(sorted(
            set(self.dependencies_by_source.get(path, ()))
            | set(self.dependents_by_dependency.get(path, ()))
        ))

    def rank_from_seed(self, seed_path: str, repository: RepositorySnapshot) -> tuple[str, ...]:
        seed = validate_repo_path(seed_path, "seed_path")
        if seed not in set(repository.list_files()):
            raise PredictionError(f"seed path is not present at parent commit: {seed}")
        result = [seed]
        seen = {seed}
        pending: deque[str] = deque([seed])
        while pending:
            dependency = pending.popleft()
            for dependent in self.dependents_by_dependency.get(dependency, ()):
                if dependent not in seen:
                    seen.add(dependent)
                    result.append(dependent)
                    pending.append(dependent)
        return tuple(result)

def historical_cochange_rank(
    repository: RepositorySnapshot, seed_path: str
) -> tuple[str, ...]:
    """Rank current files by prior non-merge commits co-changing with seed.

    Only commits returned by ``repository.history_changes()`` are inspected,
    which anchors the history to the snapshot's parent SHA. Counts sort first;
    ties break lexicographically for repeatable output.
    """
    seed = validate_repo_path(seed_path, "seed_path")
    current_files = set(repository.list_files())
    if seed not in current_files:
        raise PredictionError(f"seed path is not present at parent commit: {seed}")

    counts = historical_cochange_counts(repository, seed)
    return (seed, *sorted(counts, key=lambda path: (-counts[path], path)))

def historical_cochange_counts(
    repository: RepositorySnapshot, seed_path: str
) -> Counter[str]:
    """Count prior non-merge co-changes for files present at the snapshot."""
    seed = validate_repo_path(seed_path, "seed_path")
    current_files = set(repository.list_files())
    if seed not in current_files:
        raise PredictionError(f"seed path is not present at parent commit: {seed}")
    counts: Counter[str] = Counter()
    for _commit, paths in repository.history_changes():
        changed = set(paths)
        if seed not in changed:
            continue
        for path in changed & current_files:
            if path != seed:
                counts[path] += 1
    return counts

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

def _rank_among(query: str, repository: RepositorySnapshot, paths) -> tuple[str, ...]:
    """Rank the given paths by token overlap with the request (stable, label-free)."""
    query_tokens = Counter(token.lower() for token in _TOKEN_RE.findall(query) if len(token) > 2)
    scored: list[tuple[int, str]] = []
    for path in paths:
        source = repository.read_file(path)
        scored.append((_score_file(query_tokens, path, source), path))
    # A zero-overlap tie is stable and explicit; it does not inspect target data.
    return tuple(path for _, path in sorted(scored, key=lambda item: (-item[0], item[1])))

def _rank_sources(query: str, repository: RepositorySnapshot) -> tuple[str, ...]:
    return _rank_among(query, repository, _source_paths(repository))

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
        "Every predicted path must be unique. Never list the same file twice.\n"
        "Return fewer than 10 predictions if you cannot identify 10 distinct relevant files.\n"
        "Use exact file paths from the supplied pre-change repository tree. Do not invent paths.\n"
        "Copy each predicted path verbatim from one entry in the supplied tree, "
        "including all intermediate directories and filename capitalization. "
        "Do not construct paths from class names or infer directory locations.\n"
        "Prefer files with a direct technical connection to the reported change over "
        "files that are merely in the same package.\n\n"
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

def build_c0_constrained(
    predictor_task: PredictorInput,
    candidate_limit: int = 100,
) -> ContextDocument:
    """Build a candidate-constrained prompt from the pre-change tree."""
    if candidate_limit < 1:
        raise ValueError("candidate_limit must be positive")

    repository = predictor_task.repository
    paths = repository.list_files()

    ranked = _rank_sources(predictor_task.issue_text, repository)
    candidates = list(ranked[:candidate_limit])

    # Include non-Java files too, so documentation/configuration files
    # remain eligible for prediction.
    remaining = [
        path for path in paths
        if path not in set(candidates)
    ]
    candidates.extend(remaining[: max(0, candidate_limit - len(candidates))])

    text = (
        "You are analyzing likely file impact for a software maintenance request.\n"
        "Return only a JSON object with a 'predictions' array containing up to 10 "
        "objects of the form {\"path\": string, \"rationale\": string}, most likely first.\n"
        "Every path must be copied exactly from the candidate path list below.\n"
        "Do not output any path that is not in that list. Do not repeat paths.\n\n"
        "## Change request\n"
        + predictor_task.issue_text
        + "\n\n## Allowed candidate paths (pre-change repository)\n"
        + "\n".join(candidates)
        + "\n"
    )

    items = (
        _item(
            "issue", None, "request supplied for analysis",
            repository.commit_sha, predictor_task.issue_text,
        ),
        *(
            _item(
                "candidate_path", path,
                "candidate selected from the pre-change repository tree",
                repository.commit_sha,
            )
            for path in candidates
        ),
    )

    return ContextDocument(
        "C0_CONSTRAINED", text, repository.commit_sha, items, repository
    )

@dataclass(frozen=True, slots=True)
class _SectionLimits:
    """Character limits for the cumulative C1-C3 sections.

    ``*_per_file`` caps stop one large file from consuming a whole section budget.
    The default (``None``) reproduces the original unbounded-per-file behaviour.
    """

    source_chars: int
    dependency_chars: int
    supplementary_chars: int
    retrieved_source_limit: int
    source_per_file: int | None = None
    dependency_per_file: int | None = None
    supplementary_per_file: int | None = None
    mark_truncation: bool = False

def _clip(text: str, remaining: int, per_file: int | None, mark: bool) -> str:
    cap = remaining if per_file is None else min(remaining, per_file)
    if len(text) <= cap:
        return text
    clipped = text[:cap]
    return clipped + "\n... [truncated]" if mark else clipped

def _cumulative_contexts(
    predictor_task: PredictorInput,
    base_body: str,
    base_items: tuple[ContextItem, ...],
    limits: _SectionLimits,
    suffix: str,
    names: tuple[str, str, str],
) -> tuple[ContextDocument, ContextDocument, ContextDocument]:
    """Add C1 (source), C2 (dependency) and C3 (extended) sections onto a base body.

    Each condition adds only its own section to the previous one. ``suffix`` is a
    constant closing instruction appended to every condition's final text.
    """
    repository = predictor_task.repository
    source_rank = _rank_sources(predictor_task.issue_text, repository)
    if not source_rank:
        raise CIAError("cannot construct C1: no production Java source files exist at the parent commit")
    seed = source_rank[0]

    c1_body = base_body + "\n## Seed and retrieved source files\n"
    c1_items = list(base_items)
    selected_sources: list[str] = []
    remaining = limits.source_chars
    ordered = (seed, *(path for path in source_rank[1:] if path != seed))
    for index, path in enumerate(ordered):
        if index > limits.retrieved_source_limit:
            break
        if remaining <= 0:
            break
        source = _clip(repository.read_file(path), remaining, limits.source_per_file, limits.mark_truncation)
        selected_sources.append(path)
        kind = "seed_source" if path == seed else "retrieved_source"
        label = "SEED" if path == seed else "RETRIEVED"
        c1_body += f"\n### {label}: {path}\n```java\n{source}\n```\n"
        c1_items.append(_item(kind, path, "lexically ranked from request against parent-revision source", repository.commit_sha, source))
        remaining -= len(source)
    c1_items_tuple = tuple(c1_items)
    c1 = ContextDocument(names[0], c1_body + suffix, repository.commit_sha, c1_items_tuple, repository)

    dep_index = DependencyIndex.build(repository)
    dep_candidates: list[str] = []
    for path in selected_sources:
        for neighbor in dep_index.neighbors(path):
            if neighbor not in selected_sources and neighbor not in dep_candidates:
                dep_candidates.append(neighbor)
    c2_body = c1_body + "\n## Dependency information (parent revision)\n"
    c2_items = list(c1_items_tuple)
    remaining = limits.dependency_chars
    for path in dep_candidates:
        if remaining <= 0:
            break
        signature = _clip(_signature(repository.read_file(path)), remaining, limits.dependency_per_file, limits.mark_truncation)
        if not signature:
            continue
        c2_body += f"\n### Dependency signatures: {path}\n```java\n{signature}\n```\n"
        c2_items.append(_item(
            "dependency_signature", path,
            "direct import/type reference to or from a C1 source file", repository.commit_sha, signature,
        ))
        remaining -= len(signature)
    c2_items_tuple = tuple(c2_items)
    c2 = ContextDocument(names[1], c2_body + suffix, repository.commit_sha, c2_items_tuple, repository)

    c3_body = c2_body + "\n## Tests, documentation, and prior co-change (parent history only)\n"
    c3_items = list(c2_items_tuple)
    remaining = limits.supplementary_chars
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
        content = _clip(repository.read_file(path), remaining, limits.supplementary_per_file, limits.mark_truncation)
        if not content:
            continue
        kind = "relevant_test" if path in tests else "relevant_documentation"
        heading = "Relevant test" if kind == "relevant_test" else "Relevant documentation"
        c3_body += f"\n### {heading}: {path}\n```\n{content}\n```\n"
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
        c3_body += "\n### Prior co-change counts\n" + "\n".join(history_lines) + "\n"

    c3 = ContextDocument(names[2], c3_body + suffix, repository.commit_sha, tuple(c3_items), repository)
    return c1, c2, c3

def build_contexts(
    predictor_task: PredictorInput, budgets: ContextBudgets | None = None
) -> tuple[ContextDocument, ContextDocument, ContextDocument, ContextDocument]:
    """Build all cumulative contexts from one immutable pre-change snapshot."""
    budgets = budgets or ContextBudgets()
    base_text, base_items = _base_context(predictor_task)
    limits = _SectionLimits(
        source_chars=budgets.source_chars,
        dependency_chars=budgets.dependency_chars,
        supplementary_chars=budgets.supplementary_chars,
        retrieved_source_limit=budgets.retrieved_source_limit,
    )
    c1, c2, c3 = _cumulative_contexts(
        predictor_task, base_text, base_items, limits, "", ("C1", "C2", "C3")
    )
    return (build_c0(predictor_task), c1, c2, c3)

# ---------------------------------------------------------------------------
# Candidate-list family: C0_CAND ... C3_CAND
#
# The full-file-tree C0 prompt already uses ~26K of the 32K-token window, so the
# cumulative C1-C3 prompts built on it overflow and are silently clipped by
# Ollama. The candidate family instead keeps the model, settings and window
# fixed and builds every condition on the compact candidate list, under a hard
# per-prompt character budget, so each condition is measurably what it claims.
# ---------------------------------------------------------------------------

_NON_JAVA_TEXT_EXTENSIONS = (
    ".txt", ".md", ".rst", ".xml", ".properties", ".gradle", ".yml", ".yaml",
    ".html", ".xsl", ".cfg", ".json",
)

_CAND_SUFFIX = (
    "\n## Task\n"
    "Using the information above, return the JSON object now: up to 10 predictions, "
    "most likely first, every path copied exactly from the allowed candidate paths list.\n"
)

@dataclass(frozen=True, slots=True)
class CandidateBudgets:
    """Candidate-list composition and per-condition size limits (all label-free)."""

    candidate_limit: int = 100
    reserved_tests: int = 10
    reserved_non_java: int = 15
    source_chars: int = 32_000
    source_per_file_chars: int = 8_000
    dependency_chars: int = 10_000
    dependency_per_file_chars: int = 2_500
    supplementary_chars: int = 10_000
    supplementary_per_file_chars: int = 3_500
    retrieved_source_limit: int = 5
    max_prompt_chars: int = 72_000

    def __post_init__(self) -> None:
        if self.candidate_limit < 1:
            raise ValueError("candidate_limit must be positive")
        if self.reserved_tests < 0 or self.reserved_non_java < 0:
            raise ValueError("reserved slot counts must not be negative")
        if self.reserved_tests + self.reserved_non_java >= self.candidate_limit:
            raise ValueError("reserved slots must leave room for production Java files")
        if min(self.source_chars, self.dependency_chars, self.supplementary_chars) < 1:
            raise ValueError("section character budgets must be positive")
        if self.max_prompt_chars < 1:
            raise ValueError("max_prompt_chars must be positive")

def _is_test_path(path: str) -> bool:
    return "/test/" in f"/{path.lower()}/"

def _is_test_java(path: str) -> bool:
    return path.endswith(".java") and not path.endswith("package-info.java") and _is_test_path(path)

def _is_text_candidate(path: str) -> bool:
    if path.endswith(".java") or _is_test_path(path):
        return False
    name = path.rsplit("/", 1)[-1]
    if path.lower().endswith(_NON_JAVA_TEXT_EXTENSIONS):
        return True
    # Root-level files without an extension (README, LICENSE, NOTICE).
    return "/" not in path and "." not in name

def select_candidates(
    predictor_task: PredictorInput, budgets: CandidateBudgets | None = None
) -> tuple[tuple[str, ...], dict[str, int]]:
    """Choose the allowed candidate paths from the parent tree, without labels.

    Composition: lexically ranked production Java, a reserved block of lexically
    ranked test files, and a reserved block of non-Java text files (root-level
    documentation/build files first, then other text files by lexical rank).
    Order in the prompt: production Java, tests, non-Java.
    """
    budgets = budgets or CandidateBudgets()
    repository = predictor_task.repository
    query = predictor_task.issue_text
    paths = repository.list_files()

    production = _rank_sources(query, repository)
    tests = _rank_among(query, repository, [p for p in paths if _is_test_java(p)])
    pool = [p for p in paths if _is_text_candidate(p)]
    root_level = [p for p in pool if "/" not in p]
    nested = [p for p in pool if "/" in p]
    non_java = _rank_among(query, repository, root_level) + _rank_among(query, repository, nested)

    n_tests = min(budgets.reserved_tests, len(tests))
    n_non_java = min(budgets.reserved_non_java, len(non_java))
    n_production = budgets.candidate_limit - n_tests - n_non_java

    selected = list(production[:n_production]) + list(tests[:n_tests]) + list(non_java[:n_non_java])
    shortfall = budgets.candidate_limit - len(selected)
    if shortfall > 0:
        selected.extend(production[n_production:n_production + shortfall])
    counts = {
        "production_java": min(len(production), n_production) + max(0, min(shortfall, len(production) - n_production)),
        "test_java": n_tests,
        "non_java": n_non_java,
    }
    return tuple(selected), counts

def build_candidate_contexts(
    predictor_task: PredictorInput, budgets: CandidateBudgets | None = None
) -> tuple[ContextDocument, ContextDocument, ContextDocument, ContextDocument]:
    """Build C0_CAND..C3_CAND: the candidate list plus cumulative C1-C3 sections.

    Every prompt is guaranteed to be at most ``budgets.max_prompt_chars``.
    """
    budgets = budgets or CandidateBudgets()
    repository = predictor_task.repository
    candidates, counts = select_candidates(predictor_task, budgets)

    base_body = (
        "You are analyzing likely file impact for a software maintenance request.\n"
        "Return only a JSON object with a 'predictions' array containing up to 10 "
        "objects of the form {\"path\": string, \"rationale\": string}, most likely first.\n"
        "Every path must be copied exactly from the candidate path list below.\n"
        "Do not output any path that is not in that list. Do not repeat paths.\n\n"
        "## Change request\n"
        + predictor_task.issue_text
        + "\n\n## Allowed candidate paths (pre-change repository)\n"
        + "\n".join(candidates)
        + "\n"
    )
    base_items = (
        _item("issue", None, "request supplied for analysis", repository.commit_sha, predictor_task.issue_text),
        *(
            _item(
                "candidate_path", path,
                "candidate selected from the pre-change repository tree "
                f"(pool sizes: {counts})",
                repository.commit_sha,
            )
            for path in candidates
        ),
    )

    # Fit the three section budgets into what is left of the prompt budget,
    # keeping ~12% back for the headings and truncation markers they add.
    available = budgets.max_prompt_chars - len(base_body) - len(_CAND_SUFFIX)
    usable = int(available * 0.88)
    if usable < 3_000:
        raise CIAError(
            "prompt budget is exhausted by the issue text and candidate list; "
            "reduce candidate_limit or raise max_prompt_chars"
        )
    wanted = budgets.source_chars + budgets.dependency_chars + budgets.supplementary_chars
    scale = min(1.0, usable / wanted)
    limits = _SectionLimits(
        source_chars=max(1, int(budgets.source_chars * scale)),
        dependency_chars=max(1, int(budgets.dependency_chars * scale)),
        supplementary_chars=max(1, int(budgets.supplementary_chars * scale)),
        retrieved_source_limit=budgets.retrieved_source_limit,
        source_per_file=budgets.source_per_file_chars,
        dependency_per_file=budgets.dependency_per_file_chars,
        supplementary_per_file=budgets.supplementary_per_file_chars,
        mark_truncation=True,
    )
    c1, c2, c3 = _cumulative_contexts(
        predictor_task, base_body, base_items, limits, _CAND_SUFFIX,
        ("C1_CAND", "C2_CAND", "C3_CAND"),
    )
    c0 = ContextDocument("C0_CAND", base_body + _CAND_SUFFIX, repository.commit_sha, base_items, repository)
    contexts = (c0, c1, c2, c3)
    for context in contexts:
        if len(context.text) > budgets.max_prompt_chars:
            raise CIAError(
                f"{context.condition} prompt is {len(context.text)} characters, over the "
                f"{budgets.max_prompt_chars}-character budget"
            )
    return contexts

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
