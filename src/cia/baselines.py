"""Deterministic, lightweight change-impact baselines."""

from __future__ import annotations

import re
from collections import Counter, defaultdict, deque
from dataclasses import dataclass

from cia.errors import PredictionError
from cia.repository import RepositorySnapshot
from cia.tasks import validate_repo_path

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
        declared_by_path: dict[str, set[str]] = {}
        for path, source in sources.items():
            package_match = _PACKAGE_RE.search(source)
            package = package_match.group(1) if package_match else ""
            package_by_path[path] = package
            names = set(_TYPE_RE.findall(source))
            declared_by_path[path] = names
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

    Only commits returned by ``repository.history_commits()`` are inspected,
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

