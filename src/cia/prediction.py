"""Rank, validate, execute, and score file-impact predictions."""

from __future__ import annotations
import hashlib
import json
import time
from dataclasses import dataclass, asdict
from typing import Sequence, Any
from datetime import datetime, timezone
from cia.analysis import ContextDocument
from cia.data import PredictionError, RepositorySnapshot, validate_repo_path
from cia.providers import CompletionRequest, ModelProvider

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

@dataclass(frozen=True, slots=True)
class RankedPrediction:
    path: str
    rationale: str

@dataclass(frozen=True, slots=True)
class RunRecord:
    task_id: str
    run_kind: str
    run_started_at: str
    condition: str
    source_commit: str
    provider_name: str | None
    model_id: str | None
    model_digest: str | None
    status: str
    prompt_sha256: str
    temperature: float
    max_output_tokens: int
    latency_ms: float
    input_tokens: int | None
    output_tokens: int | None
    generation_settings: dict[str, object]
    provider_metrics: dict[str, int | float]
    predictions: tuple[RankedPrediction, ...]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["predictions"] = [asdict(item) for item in self.predictions]
        return data

def _parse_predictions(content: str, repository: RepositorySnapshot, limit: int) -> tuple[RankedPrediction, ...]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise PredictionError(f"provider response is not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("predictions"), list):
        raise PredictionError("provider response must be an object with a predictions array")
    items = payload["predictions"]
    if len(items) > limit:
        raise PredictionError(f"provider returned more than {limit} predictions")
    paths: list[str] = []
    parsed: list[RankedPrediction] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise PredictionError(f"prediction at index {index} must be an object")
        path = item.get("path")
        rationale = item.get("rationale")
        if not isinstance(path, str) or not isinstance(rationale, str) or not rationale.strip():
            raise PredictionError(f"prediction at index {index} requires string path and non-empty rationale")
        paths.append(path)
        parsed.append(RankedPrediction(path=path, rationale=rationale.strip()))
    validate_ranked_paths(paths, repository, limit=limit)
    return tuple(parsed)

def run_prediction(
    task_id: str,
    context: ContextDocument,
    provider: ModelProvider,
    *,
    temperature: float = 0.0,
    max_output_tokens: int = 1024,
    limit: int = 10,
    run_kind: str = "prediction",
) -> RunRecord:
    """Call a provider using only a context document and log outcome/usage."""
    request = CompletionRequest(
        condition=context.condition,
        prompt=context.text,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )
    prompt_hash = hashlib.sha256(context.text.encode("utf-8")).hexdigest()
    run_started_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    started = time.perf_counter()
    response_model: str | None = None
    provider_name: str | None = None
    model_digest: str | None = None
    generation_settings: dict[str, object] = {
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
    }
    provider_metrics: dict[str, int | float] = {}
    input_tokens: int | None = None
    output_tokens: int | None = None
    try:
        response = provider.complete(request)
        elapsed = (time.perf_counter() - started) * 1000
        response_model = response.model_id
        provider_name = response.provider_name
        model_digest = response.model_digest
        if response.generation_settings is not None:
            generation_settings = dict(response.generation_settings)
        if response.provider_metrics is not None:
            provider_metrics = dict(response.provider_metrics)
        input_tokens = response.input_tokens
        output_tokens = response.output_tokens
        predictions = _parse_predictions(response.content, context.repository, limit)
        return RunRecord(
            task_id=task_id, run_kind=run_kind, run_started_at=run_started_at,
            condition=context.condition, source_commit=context.commit_sha,
            provider_name=provider_name, model_id=response_model, model_digest=model_digest,
            status="ok", prompt_sha256=prompt_hash, temperature=temperature,
            max_output_tokens=max_output_tokens, latency_ms=round(elapsed, 3),
            input_tokens=input_tokens, output_tokens=output_tokens,
            generation_settings=generation_settings, provider_metrics=provider_metrics,
            predictions=predictions,
        )
    except Exception as exc:
        elapsed = (time.perf_counter() - started) * 1000
        return RunRecord(
            task_id=task_id, run_kind=run_kind, run_started_at=run_started_at,
            condition=context.condition, source_commit=context.commit_sha,
            provider_name=provider_name, model_id=response_model, model_digest=model_digest,
            status="error", prompt_sha256=prompt_hash, temperature=temperature,
            max_output_tokens=max_output_tokens, latency_ms=round(elapsed, 3),
            input_tokens=input_tokens, output_tokens=output_tokens,
            generation_settings=generation_settings, provider_metrics=provider_metrics,
            predictions=(), error=f"{type(exc).__name__}: {exc}",
        )
