"""Export draft issue texts for human review, then merge the edited texts back.

    python scripts/review_texts.py export --draft data/tasks_draft.jsonl --review-dir data/local/review
    (edit each data/local/review/<task_id>.txt in VS Code; a second member checks them)
    python scripts/review_texts.py merge --draft data/tasks_draft.jsonl --review-dir data/local/review \
        --existing data/tasks.jsonl --out data/tasks_m3.jsonl --reviewer "Name1 + Name2"

``merge`` keeps every row already in --existing unchanged (the audited pilot task),
adds the reviewed draft rows, validates the result with load_manifest, and records
the review in each row's cleaning_decisions. Review the output, then copy it over
data/tasks.jsonl. The 'flags' printed by export are hints, not a substitute for reading.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

PATCH_MARKERS = [r"^Index: ", r"^diff --git", r"^\+\+\+ ", r"^--- ", r"^@@ ", r"\bsvn diff\b", r"\bpatch attached\b", r"\battached patch\b"]


def flags_for(row: dict) -> list[str]:
    text = row["issue_text"]
    found = []
    if any(re.search(p, text, re.MULTILINE | re.IGNORECASE) for p in PATCH_MARKERS):
        found.append("POSSIBLE PATCH/DIFF TEXT")
    if re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text):
        found.append("email address")
    if re.search(r"\b(fix(ed)?|solution|workaround|should be changed|change .* to)\b", text, re.IGNORECASE):
        found.append("mentions a fix/solution (check it does not name the files to change)")
    names = [Path(p).name for p in row["changed_paths"] if p.endswith(".java")]
    hits = [n for n in names if n in text or n.removesuffix(".java") in text]
    if hits:
        found.append("names changed class(es): " + ", ".join(hits) + " (fine if it is part of the original report, e.g. a stack trace)")
    if len(text) > 1800:
        found.append(f"long ({len(text)} chars)")
    if len(text) < 80:
        found.append(f"very short ({len(text)} chars)")
    return found


def export(args: argparse.Namespace) -> int:
    rows = [json.loads(l) for l in args.draft.read_text(encoding="utf-8").splitlines() if l.strip()]
    args.review_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        (args.review_dir / f"{row['task_id']}.txt").write_text(row["issue_text"] + "\n", encoding="utf-8", newline="\n")
        print("=" * 78)
        print(f"{row['task_id']}   labels: {', '.join(row['changed_paths'])}")
        print("flags:", "; ".join(flags_for(row)) or "none")
        print("-" * 78)
        print(row["issue_text"])
    print("=" * 78)
    print(f"wrote {len(rows)} file(s) to {args.review_dir}; edit them, then run 'merge'.")
    return 0


def merge(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from cia.data import load_manifest

    existing = [json.loads(l) for l in args.existing.read_text(encoding="utf-8").splitlines() if l.strip()]
    known = {row["task_id"] for row in existing}
    drafts = [json.loads(l) for l in args.draft.read_text(encoding="utf-8").splitlines() if l.strip()]
    added = []
    for row in drafts:
        if row["task_id"] in known:
            print(f"keep existing row for {row['task_id']} (not replaced)")
            continue
        path = args.review_dir / f"{row['task_id']}.txt"
        if not path.exists():
            print(f"skip {row['task_id']}: no reviewed file at {path}")
            continue
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            print(f"skip {row['task_id']}: reviewed text is empty")
            continue
        remaining = flags_for({**row, "issue_text": text})
        if any(f.startswith("POSSIBLE PATCH") or f == "email address" for f in remaining):
            print(f"REFUSED {row['task_id']}: still contains {remaining}; fix the text first")
            continue
        row = dict(row)
        row["issue_text"] = text
        row["cleaning_decisions"] = [
            d for d in row["cleaning_decisions"] if not d.startswith(("DRAFT", "MANUAL REVIEW"))
        ] + [
            "Issue text is the Jira summary and opening problem statement, manually cleaned: follow-up discussion, "
            "contact details and any fix description removed; no patch, commit message or changed-file list is included.",
            f"Reviewed by {args.reviewer} on {date.today().isoformat()}.",
        ]
        row["selection_decision"] = row["selection_decision"].replace("DRAFT from", "From").replace(
            " Needs second-member confirmation.", " Confirmed by the reviewers named in cleaning_decisions."
        )
        added.append(row)
    out_rows = existing + added
    args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out_rows), encoding="utf-8", newline="\n")
    print(f"wrote {len(out_rows)} row(s) ({len(existing)} existing + {len(added)} new) to {args.out}")
    print(f"load_manifest accepted {len(load_manifest(str(args.out)))} row(s)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("export", "merge"):
        p = sub.add_parser(name)
        p.add_argument("--draft", type=Path, default=Path("data/tasks_draft.jsonl"))
        p.add_argument("--review-dir", type=Path, default=Path("data/local/review"))
    sub.choices["merge"].add_argument("--existing", type=Path, default=Path("data/tasks.jsonl"))
    sub.choices["merge"].add_argument("--out", type=Path, default=Path("data/tasks_m3.jsonl"))
    sub.choices["merge"].add_argument("--reviewer", required=True, help='e.g. "Atharva + Janvi"')
    args = parser.parse_args()
    return export(args) if args.command == "export" else merge(args)


if __name__ == "__main__":
    raise SystemExit(main())
