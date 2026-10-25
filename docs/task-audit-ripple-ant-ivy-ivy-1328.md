# Candidate task audit: Apache Ivy IVY-1328

**Decision: hold out from the runnable manifest pending confirmation of source
timestamp semantics and a declared reference-label policy.** This is an audit
of one Ripple candidate, not an experiment result.

## Provenance evidence

- Candidate record: Ripple artifact `assets/cia-dataset.json`, repository key
  `apache/ant-ivy`, record `instance-00001`.
- Repository: <https://github.com/apache/ant-ivy>
- Issue: <https://issues.apache.org/jira/browse/IVY-1328>
- The issue text in the Ripple record matches the ASF Jira description. The
  Jira page displays creation on 04 Jan 2012 at 12:05 and describes the HTTP
  204/HEAD failure.
- Target commit:
  `899f9fd0a9690581f33a715bb5f000397f1bafef`
- Parent commit:
  `aefb24facc745fdec7b16fa28aac6538e4a8b00c`
- The local repository resolves both objects. The target's first parent equals
  the recorded parent. The target commit is dated `2012-01-04T20:41:10Z`.
- The local Git diff reports these modified paths:
  - `CHANGES.txt`
  - `src/java/org/apache/ivy/util/url/BasicURLHandler.java`
  - `src/java/org/apache/ivy/util/url/HttpClientHandler.java`
- The existing checkout was clean during this read-only audit.

## Suitability assessment

The issue is a clear bug report and its text has a first-party ASF Jira source.
The fixed parent and target are present, and all three reported patch paths are
pre-existing files at the parent. No tests are changed in this patch.

Two uncertainties prevent treating it as verified experiment input yet:

1. The Jira page exposes a time of day but not its timezone in the inspected
   view. The target commit is later on the same UTC calendar date, so the exact
   issue-before-target ordering is not established from the displayed
   timestamp alone.
2. Ripple's `impact-set-files` label for this record contains only
   `BasicURLHandler.java`; the target Git diff contains the two Java files plus
   `CHANGES.txt`. This prototype must explicitly choose whether its reference
   label is every changed path or only eligible production Java paths. Neither
   label definition should be silently substituted for the other.

Until those decisions are resolved, this task is not added to `data/tasks.jsonl`
and must not be used for the real-task run. The issue, repository and revision
facts above are traceable; the candidate's final evaluation eligibility is
not yet established.

