"""Run one provenance-validated C0 pilot with local Ollama and baselines."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tomllib
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from cia.baselines import DependencyIndex, historical_cochange_rank
from cia.context import _rank_sources, build_c0
from cia.predictions import evaluate, validate_ranked_paths
from cia.providers.ollama import OllamaConfig, OllamaProvider
from cia.repository import RepositorySnapshot
from cia.runner import run_prediction, save_run_record
from cia.tasks import load_manifest, predictor_input


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="data/tasks.jsonl")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--config", default="config/experiment.toml")
    parser.add_argument("--output-dir", default="runs/real_task_pilot")
    args = parser.parse_args()

    records = [row for row in load_manifest(args.manifest) if row.task_id == args.task_id]
    if len(records) != 1:
        raise SystemExit(f"expected exactly one manifest task {args.task_id!r}, found {len(records)}")
    task = records[0]
    repository = RepositorySnapshot.at_commit(args.repository, task.parent_sha)
    # Validate target metadata before prediction; only the parent snapshot and
    # issue are placed in PredictorInput below.
    repository.validate_task_revision(
        task.target_sha, task.parent_sha, task.changed_paths, task.issue_created_at or ""
    )
    target_time = subprocess.run(
        ["git", "-C", str(repository.root), "show", "-s", "--format=%cI", task.target_sha],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    model_input = predictor_input(task, repository)
    context = build_c0(model_input)

    config_path = Path(args.config)
    with config_path.open("rb") as stream:
        config = tomllib.load(stream)
    local = config["models"]["local"]
    provider_config = OllamaConfig(
        model_tag=local["model_tag"], base_url=local["base_url"],
        timeout_seconds=float(local["timeout_seconds"]), num_ctx=int(local["num_ctx"]),
        seed=int(local["seed"]), top_p=float(local["top_p"]), top_k=int(local["top_k"]),
        repeat_penalty=float(local["repeat_penalty"]), response_format=local["response_format"],
    )

    seed_path = _rank_sources(task.issue_text, repository)[0]
    dependency_rank = DependencyIndex.build(repository).rank_from_seed(seed_path, repository)
    cochange_rank = historical_cochange_rank(repository, seed_path)
    max_predictions = int(config["experiment"]["prediction_limit"])
    dependency_rank = validate_ranked_paths(dependency_rank[:max_predictions], repository, max_predictions)
    cochange_rank = validate_ranked_paths(cochange_rank[:max_predictions], repository, max_predictions)

    provider = OllamaProvider(provider_config)
    run = run_prediction(
        task.task_id, context, provider,
        temperature=float(local["temperature"]), max_output_tokens=int(local["num_predict"]),
        limit=max_predictions, run_kind="one_task_real_pilot",
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    prompt_name = f"{run_id}_C0_prompt.txt"
    prompt_path = output_dir / prompt_name
    prompt_path.write_text(context.text, encoding="utf-8")
    context_manifest = {
        "task_id": task.task_id,
        "condition": "C0",
        "source_commit": context.commit_sha,
        "prompt_file": prompt_name,
        "prompt_sha256": hashlib.sha256(context.text.encode("utf-8")).hexdigest(),
        "prompt_char_count": len(context.text),
        "items": [asdict(item) for item in context.items],
    }
    context_path = output_dir / f"{run_id}_C0_context.json"
    context_path.write_text(json.dumps(context_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    predictions = [item.path for item in run.predictions]
    baselines = {
        "seed_path": seed_path,
        "seed_selection": "first deterministic lexical source rank from request text against parent snapshot",
        "dependency": {
            "ranked_paths": list(dependency_rank),
            "metrics": asdict(evaluate(dependency_rank, task.changed_paths)),
        },
        "historical_cochange": {
            "ranked_paths": list(cochange_rank),
            "history_anchor_commit": task.parent_sha,
            "metrics": asdict(evaluate(cochange_rank, task.changed_paths)),
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
            "target_first_parent": repository.first_parent(task.target_sha),
            "target_committer_at": target_time,
            "changed_paths_reference": list(task.changed_paths),
            "selection_decision": task.selection_decision,
            "cleaning_decisions": list(task.cleaning_decisions),
        },
        "predictor_input_policy": {
            "condition": "C0",
            "allowed": ["cleaned issue text", "file tree at parent commit"],
            "context_manifest": context_path.name,
            "prompt_file": prompt_name,
            "target_sha_or_patch_content_in_prompt": False,
            "ground_truth_label_list_in_prompt": False,
            "changed_paths_appear_only_as_parent_tree_entries": True,
        },
        "baselines": baselines,
        "model_run": run.to_dict(),
        "model_metrics": asdict(evaluate(predictions, task.changed_paths)) if run.status == "ok" else None,
        "artifact_created_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "limitations": [
            "One task and one C0 model call are a pilot only, not conclusive evidence.",
            "Changed-path labels are not a complete oracle for every file potentially affected.",
            "This artifact records a cleaned issue prompt; cleaning is described in the manifest.",
        ],
    }
    artifact_path = output_dir / f"{run_id}_pilot.json"
    artifact_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": run.status, "artifact": str(artifact_path), "condition": "C0", "prompt_chars": len(context.text), "seed_path": seed_path, "error": run.error}, indent=2))
    return 0 if run.status == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
