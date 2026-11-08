
"""Command-line entry point for validation, context building, and one-task runs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cia.analysis import ContextBudgets, build_contexts, save_contexts
from cia.data import CIAError, RepositorySnapshot, load_manifest, predictor_input


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cia",
        description="Repository-aware change impact analysis",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser(
        "validate-manifest",
        help="validate JSONL task rows",
    )
    validate.add_argument("manifest", type=Path)

    contexts = commands.add_parser(
        "build-contexts",
        help="validate a task and save C0-C3 inputs",
    )
    contexts.add_argument("manifest", type=Path)
    contexts.add_argument("task_id")
    contexts.add_argument("repository", type=Path)
    contexts.add_argument(
        "--output-dir",
        type=Path,
        default=Path("runs/context"),
    )
    contexts.add_argument("--source-chars", type=int, default=96_000)
    contexts.add_argument("--dependency-chars", type=int, default=24_000)
    contexts.add_argument("--supplementary-chars", type=int, default=24_000)
    contexts.add_argument("--retrieved-source-limit", type=int, default=5)

    run = commands.add_parser(
        "run-task",
        help="run one validated local-model task",
    )
    run.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/tasks.jsonl"),
    )
    run.add_argument("--task-id", required=True)
    run.add_argument("--repository", type=Path, required=True)
    run.add_argument(
        "--config",
        type=Path,
        default=Path("config/experiment.toml"),
    )
    run.add_argument(
        "--output-dir",
        type=Path,
        default=Path("runs/real_task_pilot"),
    )
    run.add_argument(
        "--condition",
        choices=["C0", "C0_CONSTRAINED", "C0_CAND", "C1_CAND", "C2_CAND", "C3_CAND"],
        default="C0",
        help="experimental prompt condition",
    )

    batch = commands.add_parser(
        "run-batch",
        help="run tasks x conditions x repeats with fixed settings and a progress log",
    )
    batch.add_argument("--manifest", type=Path, default=Path("data/tasks.jsonl"))
    batch.add_argument(
        "--task-id", action="append", dest="task_ids",
        help="task to run (repeatable); default is every task in the manifest",
    )
    batch.add_argument("--repository", type=Path, required=True)
    batch.add_argument("--config", type=Path, default=Path("config/experiment.toml"))
    batch.add_argument("--output-dir", type=Path, required=True)
    batch.add_argument(
        "--conditions", nargs="+",
        default=["C0_CAND", "C1_CAND", "C2_CAND", "C3_CAND"],
        choices=["C0", "C0_CONSTRAINED", "C0_CAND", "C1_CAND", "C2_CAND", "C3_CAND"],
    )
    batch.add_argument("--repeats", type=int, default=3)

    return parser


def _run_batch(args: argparse.Namespace) -> int:
    """Run every (task, condition, repeat); a failed run is logged, not fatal."""
    import json
    import time
    from datetime import datetime, timezone

    from cia.experiment import run_experiment

    if args.repeats < 1:
        raise CIAError("--repeats must be at least 1")
    records = load_manifest(str(args.manifest))
    wanted = args.task_ids or [record.task_id for record in records]
    known = {record.task_id for record in records}
    missing = [task_id for task_id in wanted if task_id not in known]
    if missing:
        raise CIAError(f"tasks not in manifest: {missing}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.output_dir / "batch_log.jsonl"
    total = len(wanted) * len(args.conditions) * args.repeats
    done = failures = 0
    for task_id in wanted:
        for condition in args.conditions:
            for repeat in range(1, args.repeats + 1):
                done += 1
                print(f"[{done}/{total}] {task_id} {condition} repeat {repeat}", flush=True)
                started = time.perf_counter()
                try:
                    code = run_experiment(
                        task_id=task_id,
                        repository_path=args.repository,
                        manifest_path=args.manifest,
                        config_path=args.config,
                        output_dir=args.output_dir / task_id,
                        condition=condition,
                        repeat_index=repeat,
                    )
                    error = None
                except (CIAError, ValueError, OSError, SystemExit) as exc:
                    code, error = 2, f"{type(exc).__name__}: {exc}"
                    print(f"  failed: {error}", file=sys.stderr, flush=True)
                if code != 0:
                    failures += 1
                with log_path.open("a", encoding="utf-8") as log:
                    log.write(json.dumps({
                        "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "task_id": task_id, "condition": condition, "repeat": repeat,
                        "exit_code": code, "error": error,
                        "seconds": round(time.perf_counter() - started, 1),
                    }) + "\n")
    print(f"batch finished: {done - failures}/{done} runs ok; log: {log_path}")
    return 0 if failures == 0 else 2


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "validate-manifest":
            records = load_manifest(str(args.manifest))
            print(
                f"Validated {len(records)} task record(s) "
                f"in {args.manifest}"
            )
            return 0

        if args.command == "run-task":
            from cia.experiment import run_experiment

            return run_experiment(
                task_id=args.task_id,
                repository_path=args.repository,
                manifest_path=args.manifest,
                config_path=args.config,
                output_dir=args.output_dir,
                condition=args.condition,
            )

        if args.command == "run-batch":
            return _run_batch(args)

        records = load_manifest(str(args.manifest))
        matches = [
            record for record in records
            if record.task_id == args.task_id
        ]
        if len(matches) != 1:
            raise CIAError(
                f"expected one task with id {args.task_id!r}, "
                f"found {len(matches)}"
            )

        record = matches[0]
        repository = RepositorySnapshot.at_commit(
            args.repository,
            record.parent_sha,
        )
        repository.validate_task_revision(
            record.target_sha,
            record.parent_sha,
            record.changed_paths,
            record.issue_created_at or "",
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

        manifest_path = save_contexts(
            args.output_dir,
            record.task_id,
            contexts,
        )
        print(
            f"Saved {len(contexts)} context prompts and manifests: "
            f"{manifest_path}"
        )
        return 0

    except (CIAError, ValueError, OSError) as exc:
        print(f"cia: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
