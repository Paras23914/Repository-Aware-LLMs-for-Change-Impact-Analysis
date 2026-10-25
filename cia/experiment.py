
"""Run the provenance-validated one-task local-model pilot."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tomllib
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from cia.analysis import (
    DependencyIndex,
    _rank_sources,
    build_c0,
    build_c0_constrained,
    historical_cochange_rank,
)
from cia.data import RepositorySnapshot, load_manifest, predictor_input
from cia.prediction import evaluate, run_prediction, validate_ranked_paths
from cia.providers import OllamaConfig, OllamaProvider


def run_experiment(
    task_id: str,
    repository_path: str | Path,
    manifest_path: str | Path = Path("data/tasks.jsonl"),
    config_path: str | Path = Path("config/experiment.toml"),
    output_dir: str | Path = Path("runs/real_task_pilot"),
    condition: str = "C0",
) -> int:
    """Run one validated task under the selected experimental condition."""
    if condition not in {"C0", "C0_CONSTRAINED"}:
        raise ValueError(
            f"unsupported condition {condition!r}; "
            "choose 'C0' or 'C0_CONSTRAINED'"
        )

    records = [
        row for row in load_manifest(str(manifest_path))
        if row.task_id == task_id
    ]
    if len(records) != 1:
        raise SystemExit(
            f"expected exactly one manifest task {task_id!r}, "
            f"found {len(records)}"
        )

    task = records[0]
    repository = RepositorySnapshot.at_commit(
        repository_path, task.parent_sha
    )

    # Validate target metadata before prediction. Only the parent snapshot
    # and issue are passed to the predictor.
    repository.validate_task_revision(
        task.target_sha,
        task.parent_sha,
        task.changed_paths,
        task.issue_created_at or "",
    )

    target_time = subprocess.run(
        [
            "git", "-C", str(repository.root),
            "show", "-s", "--format=%cI", task.target_sha,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    model_input = predictor_input(task, repository)

    if condition == "C0":
        context = build_c0(model_input)
    else:
        context = build_c0_constrained(model_input)

    config_path = Path(config_path)
    with config_path.open("rb") as stream:
        config = tomllib.load(stream)

    local = config["models"]["local"]
    provider_config = OllamaConfig(
        model_tag=local["model_tag"],
        base_url=local["base_url"],
        timeout_seconds=float(local["timeout_seconds"]),
        num_ctx=int(local["num_ctx"]),
        seed=int(local["seed"]),
        top_p=float(local["top_p"]),
        top_k=int(local["top_k"]),
        repeat_penalty=float(local["repeat_penalty"]),
        response_format=local["response_format"],
    )

    seed_path = _rank_sources(task.issue_text, repository)[0]
    dependency_rank = DependencyIndex.build(repository).rank_from_seed(
        seed_path, repository
    )
    cochange_rank = historical_cochange_rank(repository, seed_path)

    max_predictions = int(config["experiment"]["prediction_limit"])
    dependency_rank = validate_ranked_paths(
        dependency_rank[:max_predictions],
        repository,
        max_predictions,
    )
    cochange_rank = validate_ranked_paths(
        cochange_rank[:max_predictions],
        repository,
        max_predictions,
    )

    provider = OllamaProvider(provider_config)
    run = run_prediction(
        task.task_id,
        context,
        provider,
        temperature=float(local["temperature"]),
        max_output_tokens=int(local["num_predict"]),
        limit=max_predictions,
        run_kind="one_task_real_pilot",
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S.%fZ"
    )
    prompt_name = f"{run_id}_{condition}_prompt.txt"
    prompt_path = output_dir / prompt_name
    prompt_path.write_text(context.text, encoding="utf-8")

    context_manifest = {
        "task_id": task.task_id,
        "condition": condition,
        "source_commit": context.commit_sha,
        "prompt_file": prompt_name,
        "prompt_sha256": hashlib.sha256(
            context.text.encode("utf-8")
        ).hexdigest(),
        "prompt_char_count": len(context.text),
        "items": [asdict(item) for item in context.items],
    }

    context_path = output_dir / f"{run_id}_{condition}_context.json"
    context_path.write_text(
        json.dumps(context_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    predictions = [item.path for item in run.predictions]

    baselines = {
        "seed_path": seed_path,
        "seed_selection": (
            "first deterministic lexical source rank from request text "
            "against parent snapshot"
        ),
        "dependency": {
            "ranked_paths": list(dependency_rank),
            "metrics": asdict(
                evaluate(dependency_rank, task.changed_paths)
            ),
        },
        "historical_cochange": {
            "ranked_paths": list(cochange_rank),
            "history_anchor_commit": task.parent_sha,
            "metrics": asdict(
                evaluate(cochange_rank, task.changed_paths)
            ),
        },
    }

    artifact = {
        "artifact_type": "one_task_real_research_pilot",
        "is_synthetic": False,
        "task": {
            "task_id": task.task_id,
            "source_name": task.source_name,
            "source_url": task.source_url,
            "repository_url": task.repository_url,
            "issue_url": task.issue_url,
            "issue_text_source": task.issue_text_source,
            "issue_created_at": task.issue_created_at,
            "target_sha": task.target_sha,
            "parent_sha": task.parent_sha,
            "target_first_parent": repository.first_parent(
                task.target_sha
            ),
            "target_committer_at": target_time,
            "changed_paths_reference": list(task.changed_paths),
            "selection_decision": task.selection_decision,
            "cleaning_decisions": list(task.cleaning_decisions),
        },
        "predictor_input_policy": {
            "condition": condition,
            "allowed": (
                ["cleaned issue text", "file tree at parent commit"]
                if condition == "C0"
                else [
                    "cleaned issue text",
                    "candidate paths selected from the parent tree",
                ]
            ),
            "context_manifest": context_path.name,
            "prompt_file": prompt_name,
            "target_sha_or_patch_content_in_prompt": False,
            "ground_truth_label_list_in_prompt": False,
            "changed_paths_appear_only_as_parent_tree_entries": True,
            "constraint_type": (
                "full parent-revision file tree in prompt"
                if condition == "C0"
                else "candidate-list prompt constraint; strict validation "
                "still enforced after generation"
            ),
        },
        "baselines": baselines,
        "model_run": run.to_dict(),
        "model_metrics": (
            asdict(evaluate(predictions, task.changed_paths))
            if run.status == "ok"
            else None
        ),
        "artifact_created_at": (
            datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        ),
        "limitations": [
            "One task and one model call are a pilot only, not conclusive evidence.",
            "Changed-path labels are not a complete oracle for every file potentially affected.",
            "Issue cleaning decisions are recorded in the task manifest.",
            (
                "C0_CONSTRAINED is a candidate-list prompt condition, not a "
                "hard decoding constraint; invalid paths are still rejected."
            ),
        ],
    }

    artifact_path = output_dir / f"{run_id}_{condition}_pilot.json"
    artifact_path.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "status": run.status,
                "artifact": str(artifact_path),
                "condition": condition,
                "prompt_chars": len(context.text),
                "seed_path": seed_path,
                "error": run.error,
            },
            indent=2,
        )
    )

    return 0 if run.status == "ok" else 2
