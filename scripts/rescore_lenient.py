"""Secondary analysis: re-score runs after dropping invalid predicted paths.

Usage:
    python scripts/rescore_lenient.py runs/m3_ivy1028 runs/m3_r1 runs/m3_compress --out-dir results/m3_lenient

The primary (strict) rule in this project rejects a whole answer when any predicted
path is missing at the parent commit or duplicated. Here, for runs that were rejected,
the saved ``path_diagnostics`` are used to keep only the valid, first-occurrence paths in
their original order, and those are scored with the same metric code as the strict runs.
Runs that were ``ok`` keep their original metrics. No model is called and no prompt or
setting changes. A run whose answer had no valid path at all scores 0.

This is a sensitivity analysis. It is reported next to the strict result, never instead of it.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cia.prediction import evaluate  # noqa: E402

CONDITIONS = ["C0_CAND", "C1_CAND", "C2_CAND", "C3_CAND"]
METRICS = ("precision", "recall", "f1", "recall_at_5", "recall_at_10")


def score_run(artifact: dict) -> dict | None:
    run = artifact["model_run"]
    condition = artifact["predictor_input_policy"]["condition"]
    if condition not in CONDITIONS:
        return None
    labels = artifact["task"]["changed_paths_reference"]
    base = {
        "task_id": artifact["task"]["task_id"],
        "condition": condition,
        "strict_status": run["status"],
        "error": run.get("error") or "",
    }
    if run["status"] == "ok":
        metrics = artifact["model_metrics"]
        return {**base, "kept": len(run["predictions"]), "dropped": 0,
                **{m: metrics[m] for m in METRICS}, "lenient_applied": False}

    diagnostics = run.get("path_diagnostics")
    if not diagnostics or "paths" not in diagnostics:
        return None  # not a path-validation failure (e.g. truncation); stays a failure
    valid = [p["path"] for p in diagnostics["paths"] if p.get("valid")]
    dropped = len(diagnostics["paths"]) - len(valid)
    result = evaluate(valid, labels)
    return {**base, "kept": len(valid), "dropped": dropped,
            **{m: getattr(result, m) for m in METRICS}, "lenient_applied": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("run_dirs", nargs="+")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    rows = []
    for folder in args.run_dirs:
        for path in sorted(Path(folder).rglob("*_pilot.json")):
            row = score_run(json.loads(path.read_text(encoding="utf-8")))
            if row:
                rows.append(row)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    fields = ["task_id", "condition", "strict_status", "lenient_applied", "kept", "dropped", *METRICS, "error"]
    with (out / "lenient_runs.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: r.get(k) for k in fields} for r in rows)

    by_cond: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_cond[row["condition"]].append(row)

    def mean(vals):
        return statistics.fmean(vals) if vals else float("nan")

    lines = [
        "# Lenient re-score (secondary analysis)",
        "",
        "Strict = only fully valid answers are scored (primary). Lenient = rejected answers are "
        "scored after dropping invalid or duplicate paths. Means are over runs (one repeat per task).",
        "",
        "| Condition | Runs | Strict-ok | Strict F1 (ok only) | Lenient F1 (all runs) | Lenient R@10 | Mean paths dropped in rejected runs |",
        "|---|---|---|---|---|---|---|",
    ]
    for cond in CONDITIONS:
        group = by_cond.get(cond, [])
        if not group:
            continue
        ok = [r for r in group if r["strict_status"] == "ok"]
        rejected = [r for r in group if r["lenient_applied"]]
        lines.append(
            f"| {cond} | {len(group)} | {len(ok)} | {mean([r['f1'] for r in ok]):.3f} | "
            f"{mean([r['f1'] for r in group]):.3f} | {mean([r['recall_at_10'] for r in group]):.3f} | "
            f"{mean([r['dropped'] for r in rejected]):.1f} |"
        )
    lines += ["", "## Rejected runs after lenient scoring", ""]
    for r in rows:
        if r["lenient_applied"]:
            lines.append(
                f"- {r['task_id']} {r['condition']}: kept {r['kept']}, dropped {r['dropped']}, "
                f"F1 {r['f1']:.3f} ({r['error'][:90]})"
            )
    (out / "lenient_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {out / 'lenient_runs.csv'} and {out / 'lenient_summary.md'}")


if __name__ == "__main__":
    main()
