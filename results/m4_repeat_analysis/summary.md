# Milestone 4 analysis (from saved artifacts)

## Candidate coverage (gold paths present in the candidate list)

| Task | Gold paths | In candidates | Coverage | Java gold | Java in candidates |
|---|---|---|---|---|---|
| ant-ivy-IVY-1028 | 2 | 2 | 1.00 | 1 | 1 |
| ant-ivy-IVY-112 | 7 | 5 | 0.71 | 4 | 4 |
| ant-ivy-IVY-1141 | 3 | 0 | 0.00 | 2 | 0 |
| ant-ivy-IVY-1423 | 6 | 3 | 0.50 | 2 | 2 |
| ant-ivy-IVY-1475 | 3 | 1 | 0.33 | 2 | 1 |
| ant-ivy-IVY-1522 | 2 | 1 | 0.50 | 2 | 1 |
| ant-ivy-IVY-1531 | 3 | 2 | 0.67 | 2 | 2 |
| ant-ivy-IVY-237 | 2 | 2 | 1.00 | 1 | 1 |
| ant-ivy-IVY-248 | 2 | 2 | 1.00 | 1 | 1 |
| commons-compress-COMPRESS-119 | 3 | 3 | 1.00 | 2 | 2 |
| commons-compress-COMPRESS-276 | 8 | 8 | 1.00 | 7 | 7 |
| commons-compress-COMPRESS-469 | 4 | 3 | 0.75 | 3 | 2 |
| commons-compress-COMPRESS-74 | 2 | 2 | 1.00 | 1 | 1 |

Overall (pooled): 34/47 = 0.723; mean of per-task coverage = 0.728; Java-only 25/30 = 0.833. Maximum achievable recall is therefore this coverage, not 1.0.

## Paired strict comparison: tasks valid in all four conditions (n = 3)

Tasks: ant-ivy-IVY-1141, ant-ivy-IVY-1423, ant-ivy-IVY-1531

| Condition | Precision | Recall | F1 | R@5 | R@10 | Input tok | Output tok | Latency (s) |
|---|---|---|---|---|---|---|---|---|
| C0_CAND | 0.067 | 0.167 | 0.093 | 0.111 | 0.167 | 1657 | 528 | 14.1 |
| C1_CAND | 0.033 | 0.056 | 0.042 | 0.056 | 0.056 | 8269 | 600 | 20.0 |
| C2_CAND | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 10544 | 521 | 16.1 |
| C3_CAND | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 12735 | 561 | 18.0 |

Per-task F1 (C0, C1, C2, C3):

- ant-ivy-IVY-1141: 0.000, 0.000, 0.000, 0.000
- ant-ivy-IVY-1423: 0.125, 0.125, 0.000, 0.000
- ant-ivy-IVY-1531: 0.154, 0.000, 0.000, 0.000

## Recall among gold paths that were offered (valid runs, all tasks)

| Condition | Valid runs | Offered gold paths hit in top 10 | Offered gold paths | Rate |
|---|---|---|---|---|
| C0_CAND | 8 | 8 | 18 | 0.444 |
| C1_CAND | 11 | 8 | 31 | 0.258 |
| C2_CAND | 12 | 6 | 31 | 0.194 |
| C3_CAND | 10 | 5 | 24 | 0.208 |

## Invalid runs

| Condition | Invalid / total | Not at parent commit | Duplicate path | Other |
|---|---|---|---|---|
| C0_CAND | 5 / 13 | 4 | 1 | 0 |
| C1_CAND | 2 / 13 | 2 | 0 | 0 |
| C2_CAND | 1 / 13 | 0 | 1 | 0 |
| C3_CAND | 3 / 13 | 2 | 1 | 0 |
