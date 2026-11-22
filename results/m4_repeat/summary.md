# Repeatability check (two complete runs, same prompts and settings)

Pairs compared: 52. Present only in the first set: 0; only in the second: 0.

- Same prompt hash: 52 / 52
- Same status (ok or error): 51 / 52
- Identical ranked prediction list: 29 / 52
- Both runs valid: 41; of these, identical F1: 36
- Mean top-10 Jaccard overlap between the two runs: 0.849
- F1 absolute difference between runs (valid pairs): mean 0.0128, max 0.1667
- Output tokens, absolute difference: mean 15.0, max 103

## By condition

| Condition | Pairs | Identical ranked list | Same status | Mean top-10 Jaccard |
|---|---|---|---|---|
| C0_CAND | 13 | 4 | 13 | 0.772 |
| C1_CAND | 13 | 9 | 12 | 0.951 |
| C2_CAND | 13 | 6 | 13 | 0.775 |
| C3_CAND | 13 | 10 | 13 | 0.896 |

## Pairs that differ (23)

- ant-ivy-IVY-1028 C0_CAND: status ok->ok, F1 0.16666666666666669->0.16666666666666669, top-10 Jaccard 0.818
- ant-ivy-IVY-1028 C1_CAND: status ok->error, F1 0.16666666666666669->None, top-10 Jaccard 0.818
- ant-ivy-IVY-112 C1_CAND: status ok->ok, F1 0.125->0.125, top-10 Jaccard 1.0
- ant-ivy-IVY-112 C2_CAND: status ok->ok, F1 0.0->0.0, top-10 Jaccard 0.667
- ant-ivy-IVY-112 C3_CAND: status error->error, F1 None->None, top-10 Jaccard 0.583
- ant-ivy-IVY-1141 C2_CAND: status ok->ok, F1 0.0->0.0, top-10 Jaccard 0.583
- ant-ivy-IVY-1423 C0_CAND: status ok->ok, F1 0.125->0.125, top-10 Jaccard 0.667
- ant-ivy-IVY-1475 C2_CAND: status ok->ok, F1 0.16666666666666666->0.0, top-10 Jaccard 0.385
- ant-ivy-IVY-1522 C1_CAND: status ok->ok, F1 0.16666666666666669->0.0, top-10 Jaccard 0.818
- ant-ivy-IVY-1522 C3_CAND: status ok->ok, F1 0.0->0.16666666666666669, top-10 Jaccard 0.25
- ant-ivy-IVY-1531 C0_CAND: status ok->ok, F1 0.15384615384615383->0.15384615384615383, top-10 Jaccard 0.429
- ant-ivy-IVY-1531 C3_CAND: status ok->ok, F1 0.0->0.0, top-10 Jaccard 0.818
- ant-ivy-IVY-237 C0_CAND: status error->error, F1 None->None, top-10 Jaccard 0.667
- ant-ivy-IVY-248 C0_CAND: status ok->ok, F1 0.16666666666666669->0.16666666666666669, top-10 Jaccard 0.818
- ant-ivy-IVY-248 C2_CAND: status ok->ok, F1 0.16666666666666669->0.1818181818181818, top-10 Jaccard 0.357
- commons-compress-COMPRESS-119 C0_CAND: status error->error, F1 None->None, top-10 Jaccard 0.818
- commons-compress-COMPRESS-276 C0_CAND: status error->error, F1 None->None, top-10 Jaccard 0.462
- commons-compress-COMPRESS-276 C2_CAND: status ok->ok, F1 0.11764705882352941->0.11764705882352941, top-10 Jaccard 0.8
- commons-compress-COMPRESS-469 C0_CAND: status ok->ok, F1 0.28571428571428575->0.28571428571428575, top-10 Jaccard 0.538
- commons-compress-COMPRESS-469 C1_CAND: status ok->ok, F1 0.14285714285714288->0.15384615384615383, top-10 Jaccard 0.727
- commons-compress-COMPRESS-469 C2_CAND: status error->error, F1 None->None, top-10 Jaccard 1.0
- commons-compress-COMPRESS-74 C0_CAND: status error->error, F1 None->None, top-10 Jaccard 0.818
- commons-compress-COMPRESS-74 C2_CAND: status ok->ok, F1 0.1818181818181818->0.1818181818181818, top-10 Jaccard 0.286
