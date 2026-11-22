"""Milestone 4 analysis from saved run artifacts (no model calls).

Usage:
    python scripts/m4_analysis.py runs/m3_ivy1028 runs/m3_r1 runs/m3_compress --out-dir results/m4

Produces:
  coverage.csv / coverage in summary.md : candidate coverage per task (gold paths in the
      candidate list / all gold paths; also Java-only). The candidate list is the same for
      C0-C3, so it is read from the C0_CAND context manifest.
  paired table : metrics over the tasks that are valid (status ok) in ALL four conditions.
  covered-recall table : among valid runs, top-10 hits / gold paths that were in the candidate
      list (separates "not offered to the model" from "offered but not chosen").
  reliability table : invalid runs per condition, with cause.

The candidate list is built without labels; labels are used here only for scoring.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

CONDITIONS = ["C0_CAND", "C1_CAND", "C2_CAND", "C3_CAND"]


def load(run_dirs):
    runs = defaultdict(dict)
    contexts = {}
    for folder in run_dirs:
        for path in sorted(Path(folder).rglob("*_pilot.json")):
            artifact = json.loads(path.read_text(encoding="utf-8"))
            condition = artifact["predictor_input_policy"]["condition"]
            if condition not in CONDITIONS:
                continue
            task_id = artifact["task"]["task_id"]
            runs[task_id][condition] = artifact
            if condition == "C0_CAND":
                context = json.loads(Path(str(path).replace("_pilot.json", "_context.json")).read_text(encoding="utf-8"))
                contexts[task_id] = {i["path"] for i in context["items"] if i["kind"] == "candidate_path"}
    return runs, contexts


def mean(values):
    return statistics.fmean(values) if values else float("nan")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dirs", nargs="+")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    runs, contexts = load(args.run_dirs)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    lines = ["# Milestone 4 analysis (from saved artifacts)", ""]

    # 1. candidate coverage
    rows = []
    for task_id in sorted(runs):
        labels = runs[task_id]["C0_CAND"]["task"]["changed_paths_reference"]
        cand = contexts[task_id]
        java = [p for p in labels if p.endswith(".java")]
        rows.append({
            "task_id": task_id, "gold": len(labels), "in_candidates": sum(p in cand for p in labels),
            "gold_java": len(java), "java_in_candidates": sum(p in cand for p in java),
            "candidate_count": len(cand),
        })
    with (out / "coverage.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    total_gold = sum(r["gold"] for r in rows)
    total_in = sum(r["in_candidates"] for r in rows)
    jg = sum(r["gold_java"] for r in rows)
    ji = sum(r["java_in_candidates"] for r in rows)
    lines += ["## Candidate coverage (gold paths present in the candidate list)", "",
              "| Task | Gold paths | In candidates | Coverage | Java gold | Java in candidates |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['task_id'].replace('ripple-', '')} | {r['gold']} | {r['in_candidates']} | "
                     f"{r['in_candidates'] / r['gold']:.2f} | {r['gold_java']} | {r['java_in_candidates']} |")
    lines += ["", f"Overall (pooled): {total_in}/{total_gold} = {total_in / total_gold:.3f}; "
              f"mean of per-task coverage = {mean([r['in_candidates'] / r['gold'] for r in rows]):.3f}; "
              f"Java-only {ji}/{jg} = {ji / jg:.3f}. Maximum achievable recall is therefore this coverage, "
              "not 1.0.", ""]

    # 2. paired metrics on the tasks valid in all four conditions
    paired = [t for t in sorted(runs) if all(c in runs[t] and runs[t][c]["model_run"]["status"] == "ok" for c in CONDITIONS)]
    lines += [f"## Paired strict comparison: tasks valid in all four conditions (n = {len(paired)})", "",
              "Tasks: " + ", ".join(t.replace("ripple-", "") for t in paired), "",
              "| Condition | Precision | Recall | F1 | R@5 | R@10 | Input tok | Output tok | Latency (s) |", "|---|---|---|---|---|---|---|---|---|"]
    for c in CONDITIONS:
        metrics = [runs[t][c]["model_metrics"] for t in paired]
        model = [runs[t][c]["model_run"] for t in paired]
        lines.append(
            f"| {c} | {mean([m['precision'] for m in metrics]):.3f} | {mean([m['recall'] for m in metrics]):.3f} | "
            f"{mean([m['f1'] for m in metrics]):.3f} | {mean([m['recall_at_5'] for m in metrics]):.3f} | "
            f"{mean([m['recall_at_10'] for m in metrics]):.3f} | {mean([float(r['input_tokens']) for r in model]):.0f} | "
            f"{mean([float(r['output_tokens']) for r in model]):.0f} | {mean([float(r['latency_ms']) for r in model]) / 1000:.1f} |")
    lines += ["", "Per-task F1 (C0, C1, C2, C3):", ""]
    for t in paired:
        lines.append(f"- {t.replace('ripple-', '')}: " + ", ".join(f"{runs[t][c]['model_metrics']['f1']:.3f}" for c in CONDITIONS))
    lines.append("")

    # 3. recall among labels that were offered in the candidate list
    lines += ["## Recall among gold paths that were offered (valid runs, all tasks)", "",
              "| Condition | Valid runs | Offered gold paths hit in top 10 | Offered gold paths | Rate |", "|---|---|---|---|---|"]
    for c in CONDITIONS:
        hit = total = n = 0
        for t in runs:
            r = runs[t].get(c)
            if not r or r["model_run"]["status"] != "ok":
                continue
            n += 1
            offered = [p for p in r["task"]["changed_paths_reference"] if p in contexts[t]]
            predicted = [x["path"] for x in r["model_run"]["predictions"]][:10]
            total += len(offered)
            hit += sum(p in predicted for p in offered)
        lines.append(f"| {c} | {n} | {hit} | {total} | {hit / total:.3f} |")
    lines.append("")

    # 4. reliability
    lines += ["## Invalid runs", "", "| Condition | Invalid / total | Not at parent commit | Duplicate path | Other |", "|---|---|---|---|---|"]
    for c in CONDITIONS:
        causes = Counter()
        total = 0
        for t in runs:
            r = runs[t].get(c)
            if not r:
                continue
            total += 1
            if r["model_run"]["status"] != "ok":
                err = r["model_run"].get("error") or ""
                causes["missing" if "not present at parent" in err else "dup" if "duplicated" in err else "other"] += 1
        lines.append(f"| {c} | {sum(causes.values())} / {total} | {causes['missing']} | {causes['dup']} | {causes['other']} |")
    lines.append("")
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"wrote {out / 'summary.md'} and {out / 'coverage.csv'}")


if __name__ == "__main__":
    main()
