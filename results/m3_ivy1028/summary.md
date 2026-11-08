# Results summary

Values are the mean ± sample standard deviation **across tasks** (repeats are averaged within a task first). Only runs with status `ok` are scored; failed or clipped runs are counted separately. `R@10 (.java)` scores only the `.java` labels.

| Condition | Tasks | Runs ok / total | Precision | Recall | F1 | R@5 | R@10 | R@10 (.java) | Input tok | Output tok | Latency (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C0_CONSTRAINED | 1 | 1 / 1 | 0.100 | 0.500 | 0.167 | 0.500 | 0.500 | 1.000 | 1731 | 615 | 22.6 |
| C0_CAND | 1 | 1 / 1 | 0.100 | 0.500 | 0.167 | 0.500 | 0.500 | 1.000 | 1620 | 533 | 19.1 |
| C1_CAND | 1 | 1 / 1 | 0.100 | 0.500 | 0.167 | 0.500 | 0.500 | 1.000 | 8320 | 639 | 28.0 |
| C2_CAND | 1 | 1 / 1 | 0.100 | 0.500 | 0.167 | 0.000 | 0.500 | 1.000 | 10610 | 801 | 25.9 |
| C3_CAND | 1 | 1 / 1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 12835 | 727 | 25.0 |
| BASELINE_COCHANGE | 1 | 1 / 1 | 0.100 | 0.500 | 0.167 | 0.500 | 0.500 | 0.000 | n/a | n/a | n/a |
| BASELINE_DEPENDENCY | 1 | 1 / 1 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | n/a | n/a | n/a |

## Repeat stability (same task, same condition, repeated calls)

| Condition | Task-condition pairs with ≥2 ok repeats | Mean F1 SD across repeats | Pairs whose top-10 lists differ between repeats |
|---|---|---|---|

## Paired comparisons on F1 (per-task means; tasks scored under both)

| A | B | Tasks | Mean F1 (B − A) | B better | tie | A better |
|---|---|---|---|---|---|---|
| C0_CAND | C1_CAND | 1 | 0.000 | 0 | 1 | 0 |
| C1_CAND | C2_CAND | 1 | 0.000 | 0 | 1 | 0 |
| C2_CAND | C3_CAND | 1 | -0.167 | 0 | 0 | 1 |
| C0_CAND | C3_CAND | 1 | -0.167 | 0 | 0 | 1 |
| BASELINE_COCHANGE | C0_CAND | 1 | 0.000 | 0 | 1 | 0 |
| BASELINE_DEPENDENCY | C0_CAND | 1 | 0.167 | 1 | 0 | 0 |
| BASELINE_COCHANGE | C3_CAND | 1 | -0.167 | 0 | 0 | 1 |
| BASELINE_DEPENDENCY | C3_CAND | 1 | 0.000 | 0 | 1 | 0 |

## Failed or rejected runs: 0


Small task counts: treat differences as descriptive, not statistically established.
