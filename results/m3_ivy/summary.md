# Results summary

Values are the mean ± sample standard deviation **across tasks** (repeats are averaged within a task first). Only runs with status `ok` are scored; failed or clipped runs are counted separately. `R@10 (.java)` scores only the `.java` labels.

| Condition | Tasks | Runs ok / total | Precision | Recall | F1 | R@5 | R@10 | R@10 (.java) | Input tok | Output tok | Latency (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C0_CAND | 7 | 7 / 9 | 0.086 ± 0.038 | 0.282 ± 0.188 | 0.126 ± 0.059 | 0.282 ± 0.188 | 0.282 ± 0.188 | 0.536 ± 0.366 | 1659 ± 100 | 523 ± 38 | 14.6 ± 2.2 |
| C1_CAND | 8 | 8 / 9 | 0.064 ± 0.053 | 0.226 ± 0.236 | 0.094 ± 0.080 | 0.164 ± 0.218 | 0.226 ± 0.236 | 0.406 ± 0.421 | 8389 ± 175 | 590 ± 52 | 21.7 ± 3.7 |
| C2_CAND | 9 | 9 / 9 | 0.035 ± 0.052 | 0.148 ± 0.227 | 0.056 ± 0.083 | 0.056 ± 0.167 | 0.148 ± 0.227 | 0.278 ± 0.441 | 10655 ± 186 | 614 ± 91 | 19.2 ± 3.1 |
| C3_CAND | 7 | 7 / 9 | 0.014 ± 0.038 | 0.048 ± 0.126 | 0.022 ± 0.058 | 0.048 ± 0.126 | 0.048 ± 0.126 | 0.071 ± 0.189 | 12892 ± 371 | 585 ± 71 | 19.6 ± 2.7 |
| BASELINE_COCHANGE | 9 | 9 / 9 | 0.089 ± 0.105 | 0.254 ± 0.250 | 0.123 ± 0.133 | 0.235 ± 0.236 | 0.254 ± 0.250 | 0.139 ± 0.333 | n/a | n/a | n/a |
| BASELINE_DEPENDENCY | 9 | 9 / 9 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | n/a | n/a | n/a |

## Repeat stability (same task, same condition, repeated calls)

| Condition | Task-condition pairs with ≥2 ok repeats | Mean F1 SD across repeats | Pairs whose top-10 lists differ between repeats |
|---|---|---|---|

## Paired comparisons on F1 (per-task means; tasks scored under both)

| A | B | Tasks | Mean F1 (B − A) | B better | tie | A better |
|---|---|---|---|---|---|---|
| C0_CAND | C1_CAND | 6 | -0.024 | 1 | 4 | 1 |
| C1_CAND | C2_CAND | 8 | -0.052 | 0 | 5 | 3 |
| C2_CAND | C3_CAND | 7 | -0.026 | 0 | 5 | 2 |
| C0_CAND | C3_CAND | 5 | -0.089 | 0 | 2 | 3 |
| BASELINE_COCHANGE | C0_CAND | 7 | -0.009 | 2 | 3 | 2 |
| BASELINE_DEPENDENCY | C0_CAND | 7 | 0.126 | 6 | 1 | 0 |
| BASELINE_COCHANGE | C3_CAND | 7 | -0.079 | 1 | 3 | 3 |
| BASELINE_DEPENDENCY | C3_CAND | 7 | 0.022 | 1 | 6 | 0 |

## Failed or rejected runs: 5

- ripple-ant-ivy-IVY-112 C3_CAND repeat 1: PredictionError: predicted path is not present at parent commit: src/java/fr/jayasoft/ivy/ResolveTest.java
- ripple-ant-ivy-IVY-1475 C1_CAND repeat 1: PredictionError: predicted path is not present at parent commit: src/java/org/apache/ivy/plugins/repository/RepositoryCacheManager.java
- ripple-ant-ivy-IVY-1522 C0_CAND repeat 1: PredictionError: predicted path is duplicated: src/java/org/apache/ivy/core/resolve/IvyNode.java
- ripple-ant-ivy-IVY-237 C0_CAND repeat 1: PredictionError: predicted path is not present at parent commit: src/java/fr/jayasoft/ivy/resolver/FileSystemResolverTest.java
- ripple-ant-ivy-IVY-248 C3_CAND repeat 1: PredictionError: predicted path is not present at parent commit: src/java/fr/jayasoft/ivy/Repository.java

Small task counts: treat differences as descriptive, not statistically established.
