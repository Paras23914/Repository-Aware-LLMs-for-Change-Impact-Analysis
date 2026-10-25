"""Command-line entry point for validation, context building, and one-task runs."""

from __future__ import annotations
import argparse
import sys
from pathlib import Path
from cia.analysis import ContextBudgets, build_contexts, save_contexts
from cia.data import CIAError, RepositorySnapshot, load_manifest, predictor_input

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cia", description="Repository-aware change impact analysis")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate-manifest", help="validate JSONL task rows")
    validate.add_argument("manifest", type=Path)

    contexts = commands.add_parser("build-contexts", help="validate a task and save C0-C3 inputs")
    contexts.add_argument("manifest", type=Path)
    contexts.add_argument("task_id")
    contexts.add_argument("repository", type=Path)
    contexts.add_argument("--output-dir", type=Path, default=Path("runs/context"))
    contexts.add_argument("--source-chars", type=int, default=96_000)
    contexts.add_argument("--dependency-chars", type=int, default=24_000)
    contexts.add_argument("--supplementary-chars", type=int, default=24_000)
    contexts.add_argument("--retrieved-source-limit", type=int, default=5)
    run = commands.add_parser("run-task", help="run one validated local-model task")
    run.add_argument("--manifest", type=Path, default=Path("data/tasks.jsonl"))
    run.add_argument("--task-id", required=True)
    run.add_argument("--repository", type=Path, required=True)
    run.add_argument("--config", type=Path, default=Path("config/experiment.toml"))
    run.add_argument("--output-dir", type=Path, default=Path("runs/real_task_pilot"))
    return parser

def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        records = load_manifest(str(args.manifest))
        if args.command == "validate-manifest":
            print(f"Validated {len(records)} task record(s) in {args.manifest}")
            return 0
        if args.command == "run-task":
            from cia.experiment import run_experiment
            return run_experiment(args.task_id, args.repository, args.manifest, args.config, args.output_dir)
        matches = [record for record in records if record.task_id == args.task_id]
        if len(matches) != 1:
            raise CIAError(f"expected one task with id {args.task_id!r}, found {len(matches)}")
        record = matches[0]
        repository = RepositorySnapshot.at_commit(args.repository, record.parent_sha)
        repository.validate_task_revision(
            record.target_sha, record.parent_sha, record.changed_paths, record.issue_created_at or ""
        )
        task_input = predictor_input(record, repository)
        contexts = build_contexts(
            task_input,
            ContextBudgets(
                source_chars=args.source_chars,
                dependency_chars=args.dependency_chars,
                supplementary_chars=args.supplementary_chars,
                retrieved_source_limit=args.retrieved_source_limit,
            ),
        )
        manifest_path = save_contexts(args.output_dir, record.task_id, contexts)
        print(f"Saved {len(contexts)} context prompts and manifests: {manifest_path}")
        return 0
    except (CIAError, ValueError, OSError) as exc:
        print(f"cia: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
