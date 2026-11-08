"""Draw a seeded, stratified sample of screened tasks.

    python scripts/sample_tasks.py --csv results/screening/apache_ant-ivy_candidates.csv \
        --quota 2=3,3-5=3,6-12=2 --prepend IVY-1028 --out results/screening/chosen_keys_ivy.txt

Strata are by number of changed paths. Only rows with status ELIGIBLE and at least
--min-days between the Jira creation time and the commit are considered. The draw is
deterministic for a given CSV, seed and quota (random.Random(seed), strata in the order
given, rows in CSV order), so the selection can be reproduced and reported.
"""

from __future__ import annotations

import argparse
import csv
import random
import re
from pathlib import Path


def parse_quota(text: str) -> list[tuple[str, int, int, int]]:
    strata = []
    for part in text.split(","):
        label, count = part.split("=")
        low, _, high = label.partition("-")
        low_n = int(low.rstrip("+"))
        high_n = int(high) if high else (10**9 if label.endswith("+") else low_n)
        strata.append((label, low_n, high_n, int(count)))
    return strata


def margin_days(row: dict) -> int:
    match = re.match(r"ok \((\d+) days", row["chronology"])
    return int(match.group(1)) if match else -1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--quota", default="2=3,3-5=3,6-12=2", help="e.g. 2=3,3-5=3,6-12=2  (paths=count)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-days", type=int, default=1)
    parser.add_argument("--prepend", nargs="*", default=[], help="issue keys always included first (already audited)")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    rows = list(csv.DictReader(args.csv.open(encoding="utf-8")))
    eligible = [
        r for r in rows
        if r["status"] == "ELIGIBLE" and margin_days(r) >= args.min_days and r["issue_key"] not in args.prepend
    ]
    rng = random.Random(args.seed)
    keys = list(args.prepend)
    sizes = {}
    chosen_rows = []
    for label, low, high, count in parse_quota(args.quota):
        pool = [r for r in eligible if low <= int(r["n_changed"]) <= high]
        sizes[label] = len(pool)
        picked = rng.sample(pool, min(count, len(pool)))
        if len(picked) < count:
            print(f"warning: stratum {label} has only {len(pool)} eligible rows (wanted {count})")
        for row in picked:
            keys.append(row["issue_key"])
            chosen_rows.append((label, row))
    print(sizes, f"eligible per stratum (>= {args.min_days} day margin)\n")
    for label, row in chosen_rows:
        print(f"{label:6} {row['issue_key']:14} files={row['n_changed']:>2} changelog={row['has_changelog_label']:5} "
              f"{row['chronology'][:24]:24} {row['summary'][:55]}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(" ".join(keys), encoding="utf-8")
    print("\nKEYS:", " ".join(keys))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
