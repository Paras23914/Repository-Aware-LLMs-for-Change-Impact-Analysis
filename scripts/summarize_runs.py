"""Summarize saved run artifacts into CSV and Markdown tables.

Usage:
    python scripts/summarize_runs.py runs/m3 [runs/final_constrained_attempt ...] --out-dir results/m3

Reads every ``*_pilot.json`` under the given folders (the files written by
``python -m cia run-task`` / ``run-batch``) and writes:
    runs.csv      one row per model run, plus one row per task for each baseline
    summary.md    per-condition means, repeat stability and paired comparisons

Only standard-library modules are used. Nothing here calls a model.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

METRICS = ("precision", "recall", "f1", "recall_at_5", "recall_at_10")
ORDER = ["C0", "C0_CONSTRAINED", "C0_CAND", "C1_CAND", "C2_CAND", "C3_CAND"]


def _java_recall(paths: list[str], labels: list[str], k: int) -> float | None:
    """Recall@k over only the .java labels (None if the task has none)."""
    java_labels = [p for p in labels if p.endswith(".java")]
    if not java_labels:
        return None
    return len(set(paths[:k]) & set(java_labels)) / len(java_labels)


def _row(artifact: dict, path: Path) -> dict:
    run = artifact["model_run"]
    labels = artifact["task"]["changed_paths_reference"]
    predictions = [p["path"] for p in run.get("predictions", [])]
    metrics = artifact.get("model_metrics") or {}
    meta = artifact.get("run_meta", {})
    return {
        "task_id": artifact["task"]["task_id"],
        "condition": artifact["predictor_input_policy"]["condition"],
        "repeat": meta.get("repeat_index", 1),
        "status": run["status"],
        "error": run.get("error") or "",
        **{m: metrics.get(m) for m in METRICS},
        "recall_at_5_java_labels": _java_recall(predictions, labels, 5),
        "recall_at_10_java_labels": _java_recall(predictions, labels, 10),
        "input_tokens": run.get("input_tokens"),
        "output_tokens": run.get("output_tokens"),
        "latency_s": round(run["latency_ms"] / 1000, 2) if run.get("latency_ms") is not None else None,
        "prompt_chars": meta.get("prompt_chars"),
        "prompt_sha256": run.get("prompt_sha256"),
        "model_id": run.get("model_id"),
        "model_digest": run.get("model_digest"),
        "predictions_top10": ";".join(predictions[:10]),
        "artifact": str(path),
    }


def _baseline_rows(artifact: dict, path: Path) -> list[dict]:
    labels = artifact["task"]["changed_paths_reference"]
    rows = []
    for name, key in (("BASELINE_DEPENDENCY", "dependency"), ("BASELINE_COCHANGE", "historical_cochange")):
        block = artifact["baselines"][key]
        ranked = block["ranked_paths"]
        rows.append({
            "task_id": artifact["task"]["task_id"], "condition": name, "repeat": 1, "status": "ok",
            "error": "", **{m: block["metrics"].get(m) for m in METRICS},
            "recall_at_5_java_labels": _java_recall(ranked, labels, 5),
            "recall_at_10_java_labels": _java_recall(ranked, labels, 10),
            "input_tokens": None, "output_tokens": None, "latency_s": None,
            "prompt_chars": None, "prompt_sha256": None, "model_id": None, "model_digest": None,
            "predictions_top10": ";".join(ranked[:10]), "artifact": str(path),
        })
    return rows


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _sd(values: list[float]) -> float | None:
    return statistics.stdev(values) if len(values) > 1 else None


def _fmt(value: float | None, digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _cell(values: list[float], digits: int = 3) -> str:
    mean, sd = _mean(values), _sd(values)
    if mean is None:
        return "n/a"
    return f"{mean:.{digits}f}" + (f" ± {sd:.{digits}f}" if sd is not None else "")


def _per_task_means(rows: list[dict], metric: str) -> dict[str, float]:
    """Average repeats within a task first, so every task counts once."""
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row[metric] is not None:
            grouped[row["task_id"]].append(float(row[metric]))
    return {task: statistics.fmean(vals) for task, vals in grouped.items()}


def build_summary(rows: list[dict]) -> str:
    by_condition: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_condition[row["condition"]].append(row)
    conditions = [c for c in ORDER if c in by_condition] + sorted(
        c for c in by_condition if c not in ORDER
    )

    lines = ["# Results summary", ""]
    lines += [
        "Values are the mean ± sample standard deviation **across tasks** (repeats are averaged "
        "within a task first). Only runs with status `ok` are scored; failed or clipped runs are "
        "counted separately. `R@10 (.java)` scores only the `.java` labels.",
        "",
        "| Condition | Tasks | Runs ok / total | Precision | Recall | F1 | R@5 | R@10 | R@10 (.java) | Input tok | Output tok | Latency (s) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for condition in conditions:
        group = by_condition[condition]
        ok = [r for r in group if r["status"] == "ok"]
        tasks = {r["task_id"] for r in ok}
        cells = []
        for metric in METRICS + ("recall_at_10_java_labels", "input_tokens", "output_tokens", "latency_s"):
            per_task = list(_per_task_means(ok, metric).values())
            digits = 0 if metric in ("input_tokens", "output_tokens") else (1 if metric == "latency_s" else 3)
            cells.append(_cell(per_task, digits))
        lines.append(
            f"| {condition} | {len(tasks)} | {len(ok)} / {len(group)} | " + " | ".join(cells) + " |"
        )

    lines += ["", "## Repeat stability (same task, same condition, repeated calls)", ""]
    lines += ["| Condition | Task-condition pairs with ≥2 ok repeats | Mean F1 SD across repeats | Pairs whose top-10 lists differ between repeats |", "|---|---|---|---|"]
    for condition in conditions:
        if condition.startswith("BASELINE"):
            continue
        groups: dict[str, list[dict]] = defaultdict(list)
        for row in by_condition[condition]:
            if row["status"] == "ok":
                groups[row["task_id"]].append(row)
        multi = {t: g for t, g in groups.items() if len(g) >= 2}
        if not multi:
            continue
        sds = [statistics.pstdev([float(r["f1"]) for r in g]) for g in multi.values()]
        differ = sum(1 for g in multi.values() if len({r["predictions_top10"] for r in g}) > 1)
        lines.append(f"| {condition} | {len(multi)} | {_fmt(_mean(sds))} | {differ} of {len(multi)} |")

    lines += ["", "## Paired comparisons on F1 (per-task means; tasks scored under both)", ""]
    lines += ["| A | B | Tasks | Mean F1 (B − A) | B better | tie | A better |", "|---|---|---|---|---|---|---|"]
    pairs = [("C0_CAND", "C1_CAND"), ("C1_CAND", "C2_CAND"), ("C2_CAND", "C3_CAND"), ("C0_CAND", "C3_CAND"),
             ("BASELINE_COCHANGE", "C0_CAND"), ("BASELINE_DEPENDENCY", "C0_CAND"),
             ("BASELINE_COCHANGE", "C3_CAND"), ("BASELINE_DEPENDENCY", "C3_CAND")]
    for a, b in pairs:
        if a not in by_condition or b not in by_condition:
            continue
        fa = _per_task_means([r for r in by_condition[a] if r["status"] == "ok"], "f1")
        fb = _per_task_means([r for r in by_condition[b] if r["status"] == "ok"], "f1")
        shared = sorted(set(fa) & set(fb))
        if not shared:
            continue
        diffs = [fb[t] - fa[t] for t in shared]
        better = sum(d > 1e-9 for d in diffs)
        worse = sum(d < -1e-9 for d in diffs)
        lines.append(f"| {a} | {b} | {len(shared)} | {_fmt(statistics.fmean(diffs))} | {better} | {len(diffs) - better - worse} | {worse} |")

    failed = [r for r in rows if r["status"] != "ok" and not r["condition"].startswith("BASELINE")]
    lines += ["", f"## Failed or rejected runs: {len(failed)}", ""]
    for r in failed[:30]:
        lines.append(f"- {r['task_id']} {r['condition']} repeat {r['repeat']}: {r['error'][:160]}")
    lines += ["", "Small task counts: treat differences as descriptive, not statistically established."]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("runs", nargs="+", type=Path, help="folders containing *_pilot.json artifacts")
    parser.add_argument("--out-dir", type=Path, default=Path("results/summary"))
    args = parser.parse_args()

    files = sorted({p for folder in args.runs for p in folder.rglob("*_pilot.json")})
    if not files:
        print("no *_pilot.json artifacts found")
        return 1
    rows: list[dict] = []
    seen_baseline_tasks: set[str] = set()
    for path in files:
        artifact = json.loads(path.read_text(encoding="utf-8"))
        rows.append(_row(artifact, path))
        task = artifact["task"]["task_id"]
        if task not in seen_baseline_tasks:   # baselines are deterministic per task
            seen_baseline_tasks.add(task)
            rows.extend(_baseline_rows(artifact, path))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    with (args.out_dir / "runs.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    summary = build_summary(rows)
    (args.out_dir / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    print(f"wrote {args.out_dir / 'runs.csv'} and {args.out_dir / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
