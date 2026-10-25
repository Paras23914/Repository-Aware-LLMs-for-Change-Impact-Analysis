# Candidate task audit: Apache Ivy IVY-1028

**Decision: eligible for a one-task pilot.** This is a provenance audit, not a
claim of representative or conclusive performance.

## Sources and chronology

- Discovery record: Ripple `assets/cia-dataset.json`, repository key
  `apache/ant-ivy`, record `instance-00010`. The Ripple archive is read-only
  input; its `impact-set-files` is not used as the evaluation label.
- Repository: <https://github.com/apache/ant-ivy>
- Issue: <https://issues.apache.org/jira/browse/IVY-1028>
- Timestamp and text source: ASF Jira REST API v2
  `https://issues.apache.org/jira/rest/api/2/issue/IVY-1028?fields=created,summary,description`
- Jira `created`: `2009-02-04T03:55:38.949-05:00`.
- Target commit committer timestamp: `2009-02-10T22:02:15Z`; the Jira
  timestamp is over six days earlier.
- The original Jira summary and opening problem statement describe a failing
  snapshot dependency resolution through the `ibiblio` resolver. For prompt
  cleaning, the summary and opening technical report are retained; quoted
  mailing-list headers/contact details and follow-up discussion are omitted.

## Revision and labels

- Target: `67647ddcf1c42762dd7bc6df83ba951edad1ce93`
- Parent: `e556b3cdeb75a6ed2285f581164d76f743ab85ee`
- Git confirms the parent is the target's first parent.
- The exact Git diff path set is:
  - `CHANGES.txt`
  - `src/java/org/apache/ivy/plugins/resolver/IBiblioResolver.java`
- Both files exist at the parent revision. They are the reference labels for
  this pilot. This is the explicit all-changed-path policy, not Ripple's
  distinct impact-set annotation.

## Predictor leakage controls and suitability

The runner constructs `PredictorInput` only from the cleaned issue text and a
`RepositorySnapshot` at the fixed parent SHA. C0 includes the issue and parent
file tree only. Target SHA and changed paths are held separately for revision
validation and after-run scoring. Historical baseline reads (for C3 and the
co-change baseline) are anchored at the parent. The cleaned request is
preserved with this decision documented in `data/tasks.jsonl`.

The task is suitable for a small pilot: one focused resolver implementation
file is changed along with the changelog. Its primary limitation is label
semantics: a patch-path label measures changed paths, not every file that could
have been affected by the issue.

## Other candidate considered

IVY-1328 was held out. Its inspected Jira timestamp did not include a timezone
and was on the same date as its target commit, so ordering was not established.
Its Ripple `impact-set-files` label also differs from the complete Git diff.
The full rejection audit is preserved in the sibling research archive.
