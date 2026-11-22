"""Repeatability check: compare two complete runs of the same tasks and conditions.

Usage:
    python scripts/repeat_check.py --first runs/m3_ivy1028 runs/m3_r1 runs/m3_compress \
        --second runs/m4_repeat2 --out-dir results/m4_repeat

For every (task, condition) present in both sets it reports whether the prompt hash is
identical, the status in each run, whether the ranked predictions are identical, the top-10
overlap, the F1 difference, and the output-token and latency difference. Nothing is dropped:
a pair where either run failed is listed and counted, not hidden.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path

CONDITIONS = ["C0_CAND", "C1_CAND", "C2_CAND", "C3_CAND"]


def load(dirs):
    runs = {}
    for folder in dirs:
        for path in sorted(Path(folder).rglob("*_pilot.json")):
            artifact = json.loads(path.read_text(encoding="utf-8"))
            condition = artifact["predictor_input_policy"]["condition"]
            if condition not in CONDITIONS:
                continue
            key = (artifact["task"]["task_id"], condition)
            if key in runs:
                raise SystemExit(f"duplicate run for {key} in {folder}; pass one run per task and condition")
            runs[key] = artifact
    return runs


def predictions(artifact):
    return [item["path"] for item in artifact["model_run"].get("predictions", [])]


def raw_paths(artifact):
    """Predicted paths from path_diagnostics when the run was rejected (predictions is empty)."""
    diagnostics = artifact["model_run"].get("path_diagnostics") or {}
    return [entry["path"] for entry in diagnostics.get("paths", [])]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first", nargs="+", required=True)
    parser.add_argument("--second", nargs="+", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    first, second = load(args.first), load(args.second)
    keys = sorted(set(first) & set(second))
    missing_in_second = sorted(set(first) - set(second))
    missing_in_first = sorted(set(second) - set(first))

    rows = []
    for key in keys:
        a, b = first[key], second[key]
        ra, rb = a["model_run"], b["model_run"]
        pa = predictions(a) or raw_paths(a)
        pb = predictions(b) or raw_paths(b)
        same_prompt = ra["prompt_sha256"] == rb["prompt_sha256"]
        top_a, top_b = pa[:10], pb[:10]
        union = set(top_a) | set(top_b)
        f1a = a["model_metrics"]["f1"] if ra["status"] == "ok" else None
        f1b = b["model_metrics"]["f1"] if rb["status"] == "ok" else None
        rows.append({
            "task_id": key[0], "condition": key[1], "same_prompt_hash": same_prompt,
            "status_first": ra["status"], "status_second": rb["status"],
            "same_status": ra["status"] == rb["status"],
            "identical_ranked_list": pa == pb,
            "top10_jaccard": round(len(set(top_a) & set(top_b)) / len(union), 3) if union else 1.0,
            "f1_first": f1a, "f1_second": f1b,
            "f1_abs_diff": round(abs(f1a - f1b), 4) if f1a is not None and f1b is not None else None,
            "output_tokens_first": ra.get("output_tokens"), "output_tokens_second": rb.get("output_tokens"),
            "latency_s_first": round(float(ra["latency_ms"]) / 1000, 1), "latency_s_second": round(float(rb["latency_ms"]) / 1000, 1),
        })

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "repeat_pairs.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    n = len(rows)
    both_ok = [r for r in rows if r["status_first"] == "ok" and r["status_second"] == "ok"]
    lines = ["# Repeatability check (two complete runs, same prompts and settings)", "",
             f"Pairs compared: {n}. Present only in the first set: {len(missing_in_second)}; only in the second: {len(missing_in_first)}.", "",
             f"- Same prompt hash: {sum(r['same_prompt_hash'] for r in rows)} / {n}",
             f"- Same status (ok or error): {sum(r['same_status'] for r in rows)} / {n}",
             f"- Identical ranked prediction list: {sum(r['identical_ranked_list'] for r in rows)} / {n}",
             f"- Both runs valid: {len(both_ok)}; of these, identical F1: {sum(r['f1_abs_diff'] == 0 for r in both_ok)}",
             f"- Mean top-10 Jaccard overlap between the two runs: {statistics.fmean(r['top10_jaccard'] for r in rows):.3f}",
             ]
    diffs = [r["f1_abs_diff"] for r in both_ok if r["f1_abs_diff"] is not None]
    if diffs:
        lines.append(f"- F1 absolute difference between runs (valid pairs): mean {statistics.fmean(diffs):.4f}, max {max(diffs):.4f}")
    toks = [abs(int(r["output_tokens_first"]) - int(r["output_tokens_second"])) for r in rows
            if r["output_tokens_first"] is not None and r["output_tokens_second"] is not None]
    if toks:
        lines.append(f"- Output tokens, absolute difference: mean {statistics.fmean(toks):.1f}, max {max(toks)}")
    lines += ["", "## By condition", "", "| Condition | Pairs | Identical ranked list | Same status | Mean top-10 Jaccard |", "|---|---|---|---|---|"]
    for c in CONDITIONS:
        sub = [r for r in rows if r["condition"] == c]
        if sub:
            lines.append(f"| {c} | {len(sub)} | {sum(r['identical_ranked_list'] for r in sub)} | {sum(r['same_status'] for r in sub)} | "
                         f"{statistics.fmean(r['top10_jaccard'] for r in sub):.3f} |")
    changed = [r for r in rows if not r["identical_ranked_list"] or not r["same_status"]]
    lines += ["", f"## Pairs that differ ({len(changed)})", ""]
    for r in changed:
        lines.append(f"- {r['task_id'].replace('ripple-', '')} {r['condition']}: status {r['status_first']}->{r['status_second']}, "
                     f"F1 {r['f1_first']}->{r['f1_second']}, top-10 Jaccard {r['top10_jaccard']}")
    if missing_in_second:
        lines += ["", "Missing from second set: " + ", ".join(f"{t.replace('ripple-', '')} {c}" for t, c in missing_in_second)]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {out / 'summary.md'} and {out / 'repeat_pairs.csv'}")


if __name__ == "__main__":
    main()
