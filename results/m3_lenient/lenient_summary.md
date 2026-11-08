# Lenient re-score (secondary analysis)

Strict = only fully valid answers are scored (primary). Lenient = rejected answers are scored after dropping invalid or duplicate paths. Means are over runs (one repeat per task).

| Condition | Runs | Strict-ok | Strict F1 (ok only) | Lenient F1 (all runs) | Lenient R@10 | Mean paths dropped in rejected runs |
|---|---|---|---|---|---|---|
| C0_CAND | 13 | 8 | 0.146 | 0.156 | 0.341 | 1.4 |
| C1_CAND | 13 | 12 | 0.123 | 0.114 | 0.258 | 1.0 |
| C2_CAND | 13 | 12 | 0.094 | 0.104 | 0.221 | 4.0 |
| C3_CAND | 13 | 10 | 0.062 | 0.074 | 0.130 | 2.0 |

## Rejected runs after lenient scoring

- ripple-ant-ivy-IVY-112 C3_CAND: kept 9, dropped 1, F1 0.125 (PredictionError: predicted path is not present at parent commit: src/java/fr/jayasoft/ivy/)
- ripple-ant-ivy-IVY-1475 C1_CAND: kept 9, dropped 1, F1 0.000 (PredictionError: predicted path is not present at parent commit: src/java/org/apache/ivy/p)
- ripple-ant-ivy-IVY-1522 C0_CAND: kept 9, dropped 1, F1 0.182 (PredictionError: predicted path is duplicated: src/java/org/apache/ivy/core/resolve/IvyNod)
- ripple-ant-ivy-IVY-237 C0_CAND: kept 8, dropped 2, F1 0.200 (PredictionError: predicted path is not present at parent commit: src/java/fr/jayasoft/ivy/)
- ripple-ant-ivy-IVY-248 C3_CAND: kept 9, dropped 1, F1 0.000 (PredictionError: predicted path is not present at parent commit: src/java/fr/jayasoft/ivy/)
- ripple-commons-compress-COMPRESS-119 C0_CAND: kept 9, dropped 1, F1 0.167 (PredictionError: predicted path is not present at parent commit: src/test/java/org/apache/)
- ripple-commons-compress-COMPRESS-276 C0_CAND: kept 7, dropped 2, F1 0.133 (PredictionError: predicted path is not present at parent commit: src/test/java/org/apache/)
- ripple-commons-compress-COMPRESS-469 C2_CAND: kept 5, dropped 4, F1 0.222 (PredictionError: predicted path is duplicated: src/main/java/org/apache/commons/compress/a)
- ripple-commons-compress-COMPRESS-469 C3_CAND: kept 5, dropped 4, F1 0.222 (PredictionError: predicted path is duplicated: src/main/java/org/apache/commons/compress/a)
- ripple-commons-compress-COMPRESS-74 C0_CAND: kept 9, dropped 1, F1 0.182 (PredictionError: predicted path is not present at parent commit: src/test/java/org/apache/)
