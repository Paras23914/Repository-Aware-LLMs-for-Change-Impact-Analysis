# Results summary

Values are the mean ± sample standard deviation **across tasks** (repeats are averaged within a task first). Only runs with status `ok` are scored; failed or clipped runs are counted separately. `R@10 (.java)` scores only the `.java` labels.

| Condition | Tasks | Runs ok / total | Precision | Recall | F1 | R@5 | R@10 | R@10 (.java) | Input tok | Output tok | Latency (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C0_CAND | 1 | 1 / 4 | 0.200 | 0.500 | 0.286 | 0.500 | 0.500 | 0.667 | 1994 | 571 | 13.3 |
| C1_CAND | 4 | 4 / 4 | 0.125 ± 0.050 | 0.385 ± 0.244 | 0.182 ± 0.087 | 0.385 ± 0.244 | 0.385 ± 0.244 | 0.619 ± 0.447 | 9392 ± 533 | 610 ± 54 | 20.1 ± 2.0 |
| C2_CAND | 3 | 3 / 4 | 0.148 ± 0.064 | 0.431 ± 0.277 | 0.211 ± 0.111 | 0.431 ± 0.277 | 0.431 ± 0.277 | 0.714 ± 0.495 | 11832 ± 589 | 561 ± 23 | 17.7 ± 1.2 |
| C3_CAND | 3 | 3 / 4 | 0.111 ± 0.000 | 0.319 ± 0.188 | 0.155 ± 0.034 | 0.319 ± 0.188 | 0.319 ± 0.188 | 0.548 ± 0.431 | 14022 ± 623 | 601 ± 56 | 19.3 ± 1.6 |
| BASELINE_COCHANGE | 4 | 4 / 4 | 0.125 ± 0.096 | 0.271 ± 0.208 | 0.165 ± 0.123 | 0.208 ± 0.144 | 0.271 ± 0.208 | 0.280 ± 0.208 | n/a | n/a | n/a |
| BASELINE_DEPENDENCY | 4 | 4 / 4 | 0.025 ± 0.050 | 0.031 ± 0.062 | 0.028 ± 0.056 | 0.031 ± 0.062 | 0.031 ± 0.062 | 0.036 ± 0.071 | n/a | n/a | n/a |

## Repeat stability (same task, same condition, repeated calls)

| Condition | Task-condition pairs with ≥2 ok repeats | Mean F1 SD across repeats | Pairs whose top-10 lists differ between repeats |
|---|---|---|---|

## Paired comparisons on F1 (per-task means; tasks scored under both)

| A | B | Tasks | Mean F1 (B − A) | B better | tie | A better |
|---|---|---|---|---|---|---|
| C0_CAND | C1_CAND | 1 | -0.143 | 0 | 0 | 1 |
| C1_CAND | C2_CAND | 3 | 0.016 | 3 | 0 | 0 |
| C2_CAND | C3_CAND | 3 | -0.056 | 0 | 2 | 1 |
| BASELINE_COCHANGE | C0_CAND | 1 | 0.000 | 0 | 1 | 0 |
| BASELINE_DEPENDENCY | C0_CAND | 1 | 0.286 | 1 | 0 | 0 |
| BASELINE_COCHANGE | C3_CAND | 3 | 0.030 | 2 | 0 | 1 |
| BASELINE_DEPENDENCY | C3_CAND | 3 | 0.118 | 3 | 0 | 0 |

## Failed or rejected runs: 5

- ripple-commons-compress-COMPRESS-119 C0_CAND repeat 1: PredictionError: predicted path is not present at parent commit: src/test/java/org/apache/commons/compress/archivers/tar/TarTestCase.java
- ripple-commons-compress-COMPRESS-276 C0_CAND repeat 1: PredictionError: predicted path is not present at parent commit: src/test/java/org/apache/commons/compress/archivers/zip/UnparseableExtraFieldData.java
- ripple-commons-compress-COMPRESS-469 C2_CAND repeat 1: PredictionError: predicted path is duplicated: src/main/java/org/apache/commons/compress/archivers/zip/ZipArchiveInputStream.java
- ripple-commons-compress-COMPRESS-469 C3_CAND repeat 1: PredictionError: predicted path is duplicated: src/main/java/org/apache/commons/compress/archivers/zip/ZipArchiveInputStream.java
- ripple-commons-compress-COMPRESS-74 C0_CAND repeat 1: PredictionError: predicted path is not present at parent commit: src/test/java/org/apache/commons/compress/archivers/zip/ZipTestCase.java

Small task counts: treat differences as descriptive, not statistically established.
