"""Ranked path validation and file-level evaluation metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from cia.errors import PredictionError
from cia.repository import RepositorySnapshot
from cia.tasks import validate_repo_path


@dataclass(frozen=True, slots=True)
class Metrics:
    precision: float
    recall: float
    f1: float
    recall_at_5: float
    recall_at_10: float
    true_positives: int
    predicted_count: int
    reference_count: int


def validate_ranked_paths(
    ranked_paths: Sequence[str], repository: RepositorySnapshot, limit: int = 10
) -> tuple[str, ...]:
    if limit < 1:
        raise PredictionError("prediction limit must be positive")
    if len(ranked_paths) > limit:
        raise PredictionError(f"received {len(ranked_paths)} paths, limit is {limit}")
    available = set(repository.list_files())
    result: list[str] = []
    for raw_path in ranked_paths:
        try:
            path = validate_repo_path(raw_path, "predicted path")
        except Exception as exc:
            raise PredictionError(str(exc)) from exc
        if path not in available:
            raise PredictionError(f"predicted path is not present at parent commit: {path}")
        if path in result:
            raise PredictionError(f"predicted path is duplicated: {path}")
        result.append(path)
    return tuple(result)


def evaluate(ranked_paths: Sequence[str], reference_paths: Sequence[str], cutoff: int = 10) -> Metrics:
    if cutoff < 1:
        raise ValueError("cutoff must be positive")
    if not reference_paths:
        raise ValueError("reference_paths must not be empty")
    predicted = tuple(ranked_paths[:cutoff])
    reference = set(reference_paths)
    hits = len(set(predicted) & reference)
    precision = hits / len(predicted) if predicted else 0.0
    recall = hits / len(reference)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    def recall_at(k: int) -> float:
        return len(set(ranked_paths[:k]) & reference) / len(reference)

    return Metrics(
        precision=precision,
        recall=recall,
        f1=f1,
        recall_at_5=recall_at(5),
        recall_at_10=recall_at(10),
        true_positives=hits,
        predicted_count=len(predicted),
        reference_count=len(reference),
    )

