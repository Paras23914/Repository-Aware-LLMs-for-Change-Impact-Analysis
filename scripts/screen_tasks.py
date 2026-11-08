"""Screen RIPPLE dataset records for usable Milestone-3 task candidates.

Automates the manual audit checks (issue key, first parent, diff labels,
chronology) so a person only reviews a short table. It never calls a model.

Step 1 - screen with Git only (no network):
    python scripts/screen_tasks.py --dataset /d/cia/data/cia-dataset.json \
        --repo-key apache/ant-ivy --repository /d/cia/ant-ivy --key-prefix IVY \
        --out-dir results/screening

Step 2 - add the Jira creation-time check for the shortlist (needs internet):
    python scripts/screen_tasks.py ... --jira --jira-limit 30

Step 3 - write DRAFT manifest rows for chosen issues (cleaned text must still
be reviewed by a second member before the rows go into data/tasks.jsonl):
    python scripts/screen_tasks.py ... --emit-manifest IVY-1028 IVY-716 \
        --manifest-out data/tasks_draft.jsonl

Eligibility rules (all label-independent of any model output):
  * exactly one issue key in the commit message; when an issue has several commits
    in the dataset only the earliest is eligible (later ones are follow-ups) and
    the choice is flagged in ``notes`` for the reviewer;
  * the commit exists, is not a merge, and the dataset parent is its first parent;
  * between --min-files and --max-files changed paths;
  * at least one changed path exists at the parent (a new file can never be
    predicted from the pre-change tree) and at least one is production Java;
  * with Jira data: the issue was created before the commit (timezone-aware).
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
CHANGELOG_NAMES = {"changes.txt", "changelog", "changelog.txt", "changes.md", "changelog.md", "release_notes", "news"}
JIRA_FIELDS = "created,summary,description"


def git(repo: Path, *args: str) -> str | None:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="replace")


def is_test_path(path: str) -> bool:
    return "/test/" in f"/{path.lower()}/"


def parse_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    try:
        parsed = ast.literal_eval(value)
        return [str(v) for v in parsed] if isinstance(parsed, (list, tuple)) else []
    except (ValueError, SyntaxError):
        return []


def parse_jira_time(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%f%z")


def fetch_jira(key: str, cache_dir: Path, allow_network: bool, pause: float) -> dict | None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if not allow_network:
        return None
    url = f"https://issues.apache.org/jira/rest/api/2/issue/{key}?fields={JIRA_FIELDS}"
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "cia-course-project"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"key": key, "error": f"{type(exc).__name__}: {exc}"}
    record = {
        "key": key, "url": url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fields": payload.get("fields", {}),
    }
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    time.sleep(pause)
    return record


def inspect_record(rec: dict, repo: Path, args: argparse.Namespace) -> dict:
    commit, parent = rec["commit"], rec["parent-commit"]
    keys = sorted(set(KEY_RE.findall(rec.get("commit-message", ""))))
    if args.key_prefix:
        keys = [k for k in keys if k.startswith(args.key_prefix + "-")]
    row: dict = {
        "record_id": rec["id"], "issue_key": keys[0] if len(keys) == 1 else ";".join(keys),
        "commit": commit, "parent": parent, "commit_date": "",
        "n_changed": 0, "n_added": 0, "n_modified": 0, "n_deleted": 0,
        "n_predictable": 0, "n_prod_java_predictable": 0, "n_test_files": 0,
        "has_changelog_label": False, "impact_set_equals_diff": "", "reasons": [],
        "changed_paths": "", "summary": rec.get("issue-summary", "")[:90],
    }
    reasons: list[str] = row["reasons"]
    if len(keys) == 0:
        reasons.append("no_issue_key")
    elif len(keys) > 1:
        reasons.append("multiple_issue_keys")

    parents = git(repo, "rev-list", "--parents", "-n", "1", commit)
    if parents is None:
        reasons.append("commit_missing_locally")
        return row
    fields = parents.split()
    if len(fields) > 2:
        reasons.append("merge_commit")
    if len(fields) < 2 or fields[1] != parent:
        reasons.append("parent_is_not_first_parent")
        return row
    row["commit_date"] = (git(repo, "show", "-s", "--format=%cI", commit) or "").strip()

    raw = git(repo, "diff", "--name-status", "--no-renames", "-z", parent, commit, "--")
    tokens = [t for t in (raw or "").split("\0") if t]
    changes = list(zip(tokens[0::2], tokens[1::2]))
    paths = sorted(p for _, p in changes)
    row["changed_paths"] = ";".join(paths)
    row["n_changed"] = len(changes)
    status_counts = Counter(s[0] for s, _ in changes)
    row["n_added"], row["n_modified"], row["n_deleted"] = (status_counts["A"], status_counts["M"], status_counts["D"])
    existing = [p for s, p in changes if s[0] in "MD"]
    row["n_predictable"] = len(existing)
    row["n_prod_java_predictable"] = sum(1 for p in existing if p.endswith(".java") and not is_test_path(p))
    row["n_test_files"] = sum(1 for p in paths if is_test_path(p))
    row["has_changelog_label"] = any(p.rsplit("/", 1)[-1].lower() in CHANGELOG_NAMES for p in paths)
    row["impact_set_equals_diff"] = set(parse_list(rec.get("impact-set-files", "[]"))) == set(paths)

    if row["n_changed"] < args.min_files:
        reasons.append("too_few_changed_paths")
    if row["n_changed"] > args.max_files:
        reasons.append("too_many_changed_paths")
    if row["n_predictable"] == 0:
        reasons.append("no_label_exists_at_parent")
    if row["n_prod_java_predictable"] == 0:
        reasons.append("no_production_java_label")
    return row


def clean_description(text: str, limit: int = 1500) -> str:
    """Heuristic first pass only. A person must review the result."""
    kept: list[str] = []
    for line in (text or "").replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if re.fullmatch(r"-{3,}", stripped) or stripped.startswith("{quote}"):
            break
        if stripped.startswith(">") or re.match(r"^(From|Sent|To|Cc|Subject|Date):", stripped):
            continue
        kept.append(re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[email removed]", line))
    out = "\n".join(kept).strip()
    if len(out) > limit:
        cut = out.rfind("\n\n", 0, limit)
        out = out[: cut if cut > 200 else limit].rstrip()
    return out


def manifest_row(row: dict, rec: dict, jira: dict, repo_key: str) -> dict:
    fields = jira["fields"]
    created = parse_jira_time(fields["created"]).isoformat(timespec="milliseconds")
    key = row["issue_key"]
    description = clean_description(fields.get("description") or "")
    issue_text = fields.get("summary", "").strip() + ("\n\n" + description if description else "")
    paths = row["changed_paths"].split(";")
    return {
        "task_id": f"ripple-{repo_key.split('/')[-1]}-{key}",
        "source_name": f"Ripple issue-linked change dataset (record {rec['id']}; used for candidate discovery and cross-check only)",
        "source_url": "https://github.com/se-doubleblind/ripple",
        "repository_url": f"https://github.com/{repo_key}",
        "issue_url": f"https://issues.apache.org/jira/browse/{key}",
        "issue_text": issue_text,
        "issue_text_source": (
            f"ASF Jira REST API v2 issue {key} fields {JIRA_FIELDS}; retrieved {jira.get('retrieved_at', 'unknown')}; "
            f"{jira.get('url', '')}"
        ),
        "issue_created_at": created,
        "target_sha": row["commit"],
        "parent_sha": row["parent"],
        "changed_paths": paths,
        "selection_decision": (
            "DRAFT from scripts/screen_tasks.py: Jira creation time precedes the target commit, the recorded parent "
            "is the target's first parent, and labels are the complete parent-to-target Git diff path set. "
            "Needs second-member confirmation. Ripple impact-set-files is not used as ground truth."
        ),
        "cleaning_decisions": [
            "DRAFT: auto-extracted Jira summary and opening description; quoted/mail-header lines and email addresses removed by heuristic.",
            "MANUAL REVIEW REQUIRED: remove follow-up discussion and contact details, and confirm the text contains no patch, fix description or changed-file list.",
            "Ground truth is the exact Git diff path set from parent to target; do not substitute Ripple impact-set-files.",
        ],
        "suitability_notes": [
            f"{row['n_changed']} changed paths, {row['n_predictable']} exist at the parent revision "
            f"({row['n_prod_java_predictable']} production Java).",
        ] + (["Labels include a changelog file."] if row["has_changelog_label"] else []) + row["notes"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--repo-key", required=True, help="dataset key, e.g. apache/ant-ivy")
    parser.add_argument("--repository", type=Path, required=True, help="full local clone of that repository")
    parser.add_argument("--key-prefix", help="only count issue keys with this prefix, e.g. IVY")
    parser.add_argument("--out-dir", type=Path, default=Path("results/screening"))
    parser.add_argument("--min-files", type=int, default=2)
    parser.add_argument("--max-files", type=int, default=12)
    parser.add_argument("--jira", action="store_true", help="fetch Jira creation times (internet) for the shortlist")
    parser.add_argument("--jira-limit", type=int, default=30, help="max issues to fetch from Jira")
    parser.add_argument("--jira-cache", type=Path, default=Path("data/local/jira_cache"))
    parser.add_argument("--emit-manifest", nargs="+", metavar="KEY")
    parser.add_argument("--manifest-out", type=Path, default=Path("data/tasks_draft.jsonl"))
    args = parser.parse_args()

    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    if args.repo_key not in dataset:
        print(f"repo key {args.repo_key!r} not in dataset; choose from: {sorted(dataset)}")
        return 2
    records = dataset[args.repo_key]
    rows = [inspect_record(rec, args.repository, args) for rec in records]
    by_id = {rec["id"]: rec for rec in records}

    by_issue: dict[str, list[dict]] = {}
    for row in rows:
        if row["issue_key"] and ";" not in row["issue_key"]:
            by_issue.setdefault(row["issue_key"], []).append(row)
    for row in rows:
        row["notes"] = []
    for issue_rows in by_issue.values():
        if len(issue_rows) < 2:
            continue
        issue_rows.sort(key=lambda r: r["commit_date"] or "9999")
        issue_rows[0]["notes"].append(f"issue has {len(issue_rows)} commits in the dataset; earliest kept")
        for later in issue_rows[1:]:
            later["reasons"].append("later_commit_for_same_issue")

    # Jira chronology for rows that passed every Git check.
    shortlist = [r for r in rows if not r["reasons"]]
    shortlist.sort(key=lambda r: (r["n_changed"], r["commit_date"]))
    jira_checked = 0
    for row in shortlist:
        cached = fetch_jira(row["issue_key"], args.jira_cache, False, 0)
        if cached is None and args.jira and jira_checked < args.jira_limit:
            cached = fetch_jira(row["issue_key"], args.jira_cache, True, 0.5)
            jira_checked += 1
        row["jira_created"] = ""
        row["chronology"] = "unchecked"
        if cached and "fields" in cached and cached["fields"].get("created"):
            created = parse_jira_time(cached["fields"]["created"])
            commit_time = datetime.fromisoformat(row["commit_date"])
            row["jira_created"] = cached["fields"]["created"]
            if created < commit_time:
                row["chronology"] = f"ok ({(commit_time - created).days} days before commit)"
            else:
                row["chronology"] = "FAIL: issue created after commit"
                row["reasons"].append("issue_not_before_commit")
        elif cached and "error" in cached:
            row["chronology"] = "jira_error"

    for row in rows:
        row.setdefault("jira_created", "")
        row.setdefault("chronology", "")
        if row["reasons"]:
            row["status"] = "EXCLUDED"
        elif row["chronology"].startswith("ok"):
            row["status"] = "ELIGIBLE"
        else:
            row["status"] = "ELIGIBLE_PENDING_JIRA"
    order = {"ELIGIBLE": 0, "ELIGIBLE_PENDING_JIRA": 1, "EXCLUDED": 2}
    rows.sort(key=lambda r: (order[r["status"]], r["n_changed"], r["commit_date"]))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = args.out_dir / f"{args.repo_key.replace('/', '_')}_candidates.csv"
    columns = ["status", "issue_key", "n_changed", "n_predictable", "n_prod_java_predictable", "n_test_files",
               "has_changelog_label", "impact_set_equals_diff", "chronology", "jira_created", "commit_date",
               "reasons", "notes", "summary", "changed_paths", "record_id", "commit", "parent"]
    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "reasons": ";".join(row["reasons"]), "notes": ";".join(row["notes"])})

    counts = Counter(r["status"] for r in rows)
    reason_counts = Counter(reason for r in rows for reason in r["reasons"])
    print(f"{len(rows)} records screened -> {out_csv}")
    print("status:", dict(counts))
    print("exclusion reasons:", dict(reason_counts.most_common()))
    print(f"impact-set-files equals the Git diff in {sum(1 for r in rows if r['impact_set_equals_diff'] is True)} of {len(rows)} records")

    if args.emit_manifest:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        written = []
        for key in args.emit_manifest:
            row = next((r for r in rows if r["issue_key"] == key and r["status"] != "EXCLUDED"), None)
            if row is None:
                print(f"skip {key}: not in the eligible set")
                continue
            jira = fetch_jira(key, args.jira_cache, args.jira, 0.5)
            if not jira or "fields" not in jira:
                print(f"skip {key}: no Jira data (run with --jira first)")
                continue
            written.append(manifest_row(row, by_id[row["record_id"]], jira, args.repo_key))
        args.manifest_out.parent.mkdir(parents=True, exist_ok=True)
        with args.manifest_out.open("w", encoding="utf-8", newline="\n") as handle:
            for item in written:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"wrote {len(written)} DRAFT rows to {args.manifest_out}")
        try:
            from cia.data import load_manifest
            print(f"load_manifest accepted {len(load_manifest(str(args.manifest_out)))} row(s)")
        except Exception as exc:  # noqa: BLE001
            print(f"load_manifest check failed: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
