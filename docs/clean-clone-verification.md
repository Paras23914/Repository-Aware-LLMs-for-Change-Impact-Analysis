# Clean-clone verification (Milestone 4)

Performed on 2026-11-22 by Sheikh Fraz Alam, in a fresh clone on the shared laptop.

- Clone: commit 88d9206 (main, equal to origin/main)
- Python 3.11.9, new virtual environment, `pip install -e .` succeeded
- `python -m unittest discover -s tests`: 21 tests, OK
- `python -m cia validate-manifest data/tasks.jsonl`: validated 13 task records
- `python scripts/m4_analysis.py runs/m3_ivy1028 runs/m3_r1 runs/m3_compress`: summary.md identical (diff) to committed results/m4/summary.md

Not covered: this does not re-run the model; repeatability of model runs is reported separately (results/m4_repeat).
