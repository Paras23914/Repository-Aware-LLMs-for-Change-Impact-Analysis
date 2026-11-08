# Results summary

Values are the mean ± sample standard deviation **across tasks** (repeats are averaged within a task first). Only runs with status `ok` are scored; failed or clipped runs are counted separately. `R@10 (.java)` scores only the `.java` labels.

| Condition | Tasks | Runs ok / total | Precision | Recall | F1 | R@5 | R@10 | R@10 (.java) | Input tok | Output tok | Latency (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C0_CAND | 8 | 8 / 13 | 0.100 ± 0.053 | 0.310 ± 0.190 | 0.146 ± 0.078 | 0.310 ± 0.190 | 0.310 ± 0.190 | 0.552 ± 0.342 | 1701 ± 150 | 529 ± 39 | 14.5 ± 2.1 |
| C1_CAND | 12 | 12 / 13 | 0.084 ± 0.058 | 0.279 ± 0.240 | 0.123 ± 0.089 | 0.238 ± 0.242 | 0.279 ± 0.240 | 0.477 ± 0.422 | 8723 ± 584 | 597 ± 51 | 21.2 ± 3.2 |
| C2_CAND | 12 | 12 / 13 | 0.063 ± 0.073 | 0.219 ± 0.261 | 0.094 ± 0.111 | 0.149 ± 0.251 | 0.219 ± 0.261 | 0.387 ± 0.474 | 10949 ± 610 | 601 ± 82 | 18.8 ± 2.8 |
| C3_CAND | 10 | 10 / 13 | 0.043 ± 0.056 | 0.129 ± 0.189 | 0.062 ± 0.082 | 0.129 ± 0.189 | 0.129 ± 0.189 | 0.214 ± 0.343 | 13231 ± 690 | 590 ± 64 | 19.5 ± 2.3 |
| BASELINE_COCHANGE | 13 | 13 / 13 | 0.100 ± 0.100 | 0.259 ± 0.230 | 0.136 ± 0.127 | 0.227 ± 0.206 | 0.259 ± 0.230 | 0.182 ± 0.299 | n/a | n/a | n/a |
| BASELINE_DEPENDENCY | 13 | 13 / 13 | 0.008 ± 0.028 | 0.010 ± 0.035 | 0.009 ± 0.031 | 0.010 ± 0.035 | 0.010 ± 0.035 | 0.011 ± 0.040 | n/a | n/a | n/a |

## Repeat stability (same task, same condition, repeated calls)

| Condition | Task-condition pairs with ≥2 ok repeats | Mean F1 SD across repeats | Pairs whose top-10 lists differ between repeats |
|---|---|---|---|

## Paired comparisons on F1 (per-task means; tasks scored under both)

| A | B | Tasks | Mean F1 (B − A) | B better | tie | A better |
|---|---|---|---|---|---|---|
| C0_CAND | C1_CAND | 7 | -0.041 | 1 | 4 | 2 |
| C1_CAND | C2_CAND | 11 | -0.034 | 3 | 5 | 3 |
| C2_CAND | C3_CAND | 10 | -0.035 | 0 | 7 | 3 |
| C0_CAND | C3_CAND | 5 | -0.089 | 0 | 2 | 3 |
| BASELINE_COCHANGE | C0_CAND | 8 | -0.007 | 2 | 4 | 2 |
| BASELINE_DEPENDENCY | C0_CAND | 8 | 0.146 | 7 | 1 | 0 |
| BASELINE_COCHANGE | C3_CAND | 10 | -0.046 | 3 | 3 | 4 |
| BASELINE_DEPENDENCY | C3_CAND | 10 | 0.051 | 4 | 6 | 0 |

## Failed or rejected runs: 10

- ripple-commons-compress-COMPRESS-119 C0_CAND repeat 1: PredictionError: predicted path is not present at parent commit: src/test/java/org/apache/commons/compress/archivers/tar/TarTestCase.java
- ripple-commons-compress-COMPRESS-276 C0_CAND repeat 1: PredictionError: predicted path is not present at parent commit: src/test/java/org/apache/commons/compress/archivers/zip/UnparseableExtraFieldData.java
- ripple-commons-compress-COMPRESS-469 C2_CAND repeat 1: PredictionError: predicted path is duplicated: src/main/java/org/apache/commons/compress/archivers/zip/ZipArchiveInputStream.java
- ripple-commons-compress-COMPRESS-469 C3_CAND repeat 1: PredictionError: predicted path is duplicated: src/main/java/org/apache/commons/compress/archivers/zip/ZipArchiveInputStream.java
- ripple-commons-compress-COMPRESS-74 C0_CAND repeat 1: PredictionError: predicted path is not present at parent commit: src/test/java/org/apache/commons/compress/archivers/zip/ZipTestCase.java
- ripple-ant-ivy-IVY-112 C3_CAND repeat 1: PredictionError: predicted path is not present at parent commit: src/java/fr/jayasoft/ivy/ResolveTest.java
- ripple-ant-ivy-IVY-1475 C1_CAND repeat 1: PredictionError: predicted path is not present at parent commit: src/java/org/apache/ivy/plugins/repository/RepositoryCacheManager.java
- ripple-ant-ivy-IVY-1522 C0_CAND repeat 1: PredictionError: predicted path is duplicated: src/java/org/apache/ivy/core/resolve/IvyNode.java
- ripple-ant-ivy-IVY-237 C0_CAND repeat 1: PredictionError: predicted path is not present at parent commit: src/java/fr/jayasoft/ivy/resolver/FileSystemResolverTest.java
- ripple-ant-ivy-IVY-248 C3_CAND repeat 1: PredictionError: predicted path is not present at parent commit: src/java/fr/jayasoft/ivy/Repository.java

Small task counts: treat differences as descriptive, not statistically established.
