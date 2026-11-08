# Repository-Aware Change Impact Analysis

How do the amount and type of repository context given to an LLM affect its prediction of the files impacted by a software change? This repository holds a reproducible pipeline and the evidence for that question: a fixed local model, Qwen2.5-Coder 7B (`qwen2.5-coder:7b` through Ollama), is given a cleaned issue text and progressively more context, and its ranked list of impacted files is compared with the files changed by the real fix.

Course project for ENGR 5570G (Software Maintenance and Evolution), Fall 2026, Dr. Kundi Yao.

- **Project track: Applied.** This is an applied empirical study of LLM-based change impact analysis on real projects. It is not a replication of a published study. The RIPPLE dataset is used only to discover candidate tasks, and the labels and the experiment are our own.
- **Group 6:** Paras Sharma, Atharva Rajadhyaksha, Amala Gopinath, Janvi Naresh Gurfude, Sheikh Fraz Alam.

## Project status (Milestone 3)

- **13 tasks in two Apache repositories:** 9 from Apache Ivy (the audited pilot task IVY-1028 plus 8 drawn tasks) and 4 from Apache Commons Compress. Tasks were screened with fixed rules and drawn with a seeded, stratified sampler (seed 42, strata by number of changed paths).
- **Four context conditions, one run per task and condition (52 model runs):** C0_CAND, C1_CAND, C2_CAND, C3_CAND (see below).
- **Main observation (descriptive only):** in this setup more context did not improve file-level prediction. Mean F1 over valid runs fell from 0.146 (C0_CAND) to 0.062 (C3_CAND) while input grew from about 1.7k to 13.2k tokens; a no-model co-change baseline scored 0.136. Ten of 52 runs were rejected because the model named a path that does not exist at the parent commit or repeated a path, and a lenient re-score keeps the same ordering. With 13 tasks and one run per cell, differences are not statistically established.
- **Not done yet:** repeated runs to measure run-to-run variation, more repositories, and tests of why more context did not help. See Limitations.

Full tables: [`results/m3_all/summary.md`](results/m3_all/summary.md) (all tasks), [`results/m3_ivy/`](results/m3_ivy/) and [`results/m3_compress/`](results/m3_compress/) (per repository), [`results/m3_lenient/`](results/m3_lenient/) (secondary lenient re-score).

## Model input (and what changed since Milestone 2)

For every task the model receives **only** a cleaned issue text and information taken from the repository **at the parent commit** (the state before the fix). It never sees the target patch, commit message, label paths or any post-fix content. It must answer with JSON: up to 10 ranked `{path, rationale}` objects whose paths are copied exactly from an allowed candidate list.

| | Milestone 2 | Milestone 3 |
|---|---|---|
| Conditions | `C0` (issue + whole file tree) and `C0_CONSTRAINED` (issue + candidate list) | `C0_CAND` to `C3_CAND`, run on every task |
| Candidate list | top 100 **non-test Java** files, ranked by token overlap with the issue; non-Java files only as padding, so for Ivy the list contained none (this capped recall at 0.50 on IVY-1028) | 100 files with reserved blocks: up to 75 production Java, up to 10 test Java, up to 15 non-Java text files (root-level documentation and build files first), all chosen without looking at labels |
| Context beyond issue and list | none | `C1`: source of up to 5 retrieved files; `C2`: + dependency signatures; `C3`: + related tests, documentation and parent-bounded co-change history |
| Prompt size | `C0` prompt 88,402 characters; `C1`-`C3` prompts exported but never scored, and they exceeded the context window (silently clipped by Ollama) | 6k to 62k characters per prompt, checked by size guards before and after every call |
| Tasks | 1 | 13 (9 Ivy, 4 Commons Compress) |
| Issue text | cleaned by hand for 1 task | cleaned and reviewed for all 13 (patch markers, e-mail addresses and fix details removed; recorded in `cleaning_decisions`) |

Shared by both milestones: model `qwen2.5-coder:7b` (digest `dae161e27b0e`), temperature 0, seed 42, top-p 1.0, top-k 40, repeat penalty 1.0, context length 32,768, at most 2,048 output tokens.

## Requirements

- Python 3.11 or newer and Git on `PATH`
- Local clones of the study repositories (the pipeline reads the parent and target commits):
  - `https://github.com/apache/ant-ivy`
  - `https://github.com/apache/commons-compress`
- [Ollama](https://ollama.com) with `qwen2.5-coder:7b` (digest `dae161e27b0e`, Q4_K_M) for model runs
- The RIPPLE dataset file `assets/cia-dataset.json` from `https://github.com/se-doubleblind/ripple`, only if you want to repeat the screening step

The analysis scripts and unit tests use only the Python standard library and need no network, Ollama or API key.

## Setup and checks

```bash
python -m pip install -e .
python -m unittest discover -s tests -v          # 21 tests
python -m cia validate-manifest data/tasks.jsonl  # 13 task records
```

Model and server details recorded for this study are in [`docs/model-info.txt`](docs/model-info.txt). Settings are in [`config/experiment.toml`](config/experiment.toml): temperature 0, seed 42, top-p 1.0, top-k 40, repeat penalty 1.0, context length 32,768, at most 2,048 generated tokens, JSON output.

## Running the study

Run all four conditions for chosen tasks (one repeat; set `--repeats` for more):

```bash
python -m cia run-batch --repository /path/to/ant-ivy --output-dir runs/m3_r1 --repeats 1 \
  --task-id ripple-ant-ivy-IVY-1522 --task-id ripple-ant-ivy-IVY-1475

python -m cia run-batch --repository /path/to/commons-compress --output-dir runs/m3_compress --repeats 1 \
  --task-id ripple-commons-compress-COMPRESS-74 --task-id ripple-commons-compress-COMPRESS-119
```

Run a single condition for a single task:

```bash
python -m cia run-task --task-id ripple-ant-ivy-IVY-1028 --repository /path/to/ant-ivy --condition C0_CAND
```

Summarize saved runs (writes `runs.csv` and `summary.md`; calls no model) and the lenient re-score:

```bash
python scripts/summarize_runs.py runs/m3_ivy1028 runs/m3_r1 runs/m3_compress --out-dir results/m3_all
python scripts/rescore_lenient.py runs/m3_ivy1028 runs/m3_r1 runs/m3_compress --out-dir results/m3_lenient
```

Repeat the task selection (needs the dataset and Jira access; Jira responses are cached under `data/local/`):

```bash
python scripts/screen_tasks.py --dataset /path/to/cia-dataset.json --repo-key apache/commons-compress \
  --repository /path/to/commons-compress --key-prefix COMPRESS --out-dir results/screening --jira --jira-limit 200
python scripts/sample_tasks.py --csv results/screening/apache_commons-compress_candidates.csv \
  --quota 2=1,3-5=2,6-12=1 --seed 42 --min-days 1 --out results/screening/chosen_keys_compress.txt
```

Issue texts were exported, cleaned and reviewed by hand with `scripts/review_texts.py` before being merged into `data/tasks.jsonl`.

## Conditions

All four conditions share one label-free candidate list of 100 files built from the parent snapshot and the issue text only (up to 75 production Java files, up to 10 test files and up to 15 non-Java text files, in that order). The model ranks up to 10 paths from it. Conditions are cumulative:

| Condition | Adds |
|---|---|
| `C0_CAND` | cleaned issue text and the candidate list |
| `C1_CAND` | source of up to 5 retrieved files (8,000 characters each at most) |
| `C2_CAND` | signatures of dependency-related files |
| `C3_CAND` | related tests, documentation and parent-bounded co-change partners |

Each section has a character budget. Prompts range from about 6k characters (C0) to about 62k (C3).

**Context-window guard.** Ollama silently truncates prompts that exceed the context window. The Milestone 2 context prompts (about 185k to 235k characters) were reported as only 16,386 tokens, so the model had seen clipped text. [`cia/guards.py`](cia/guards.py) refuses oversized prompts before the call and marks a run as an error if its characters-per-token ratio is implausible. The earlier `C0` and `C0_CONSTRAINED` conditions are kept unchanged for the Milestone 2 record.

**Baselines.** The dependency baseline (import-graph neighbours of a seed file) and the historical co-change baseline both start from a seed file chosen lexically from the issue. That seed is often wrong, so the baselines are reference points and not tuned competitors.

**Scoring.** Labels are the exact paths of the parent-to-target Git diff, not RIPPLE's `impact-set-files` field (the two agree in only 6 of 177 Ivy and 10 of 59 Compress records). Labels therefore include non-Java files such as `CHANGES.txt`; recall over Java labels is reported separately. Strict rule: an answer is scored only if every predicted path exists at the parent commit and none is repeated; otherwise it is recorded as rejected. `scripts/rescore_lenient.py` shows a secondary re-score that drops only the invalid paths of rejected runs.

## Data provenance

- Task candidates come from the RIPPLE change-impact dataset (`se-doubleblind/ripple`, 25 Apache repositories, 866 records), used for discovery and cross-checking only.
- Screening rules (decided before any model call on the sampled tasks): one Jira key per commit, non-merge first-parent commit, 2 to 12 changed paths, earliest commit per issue, and at least one day between Jira creation and the commit. Results: [`results/screening/`](results/screening/).
- Task manifest: [`data/tasks.jsonl`](data/tasks.jsonl) (schema in `data/task.schema.json`). It records source, revisions and the cleaning decisions for every issue text. The drafts and merge intermediates are kept as `data/tasks_draft*.jsonl` and `data/tasks_m3*.jsonl`.
- Pilot task audit: [`docs/task-audit-ripple-ant-ivy-ivy-1028.md`](docs/task-audit-ripple-ant-ivy-ivy-1028.md).
- The target diff, commit message, label paths and post-target repository content are never part of the model input.

## Experiment artifacts

Each run folder holds, per task and condition, the prompt, a context manifest and a result JSON with the model digest, prompt hash, settings, token counts, latency, predictions, path diagnostics, raw model response and metrics.

- [`runs/m3_ivy1028/`](runs/m3_ivy1028/): IVY-1028, four conditions
- [`runs/m3_r1/`](runs/m3_r1/): 8 further Ivy tasks, four conditions each
- [`runs/m3_compress/`](runs/m3_compress/): 4 Commons Compress tasks, four conditions each
- [`runs/final_c0_attempt/`](runs/final_c0_attempt/) and [`runs/final_constrained_attempt/`](runs/final_constrained_attempt/): Milestone 2 pilot attempts, kept unchanged

## Limitations

- 13 tasks, two Java projects, one model, and one run per task and condition. There is no measure of run-to-run variation, and no significance test.
- 10 of 52 runs were rejected (5 in C0, 1 in C1, 1 in C2, 3 in C3), so strict condition means cover different task sets. Paired comparisons and the lenient re-score reduce but do not remove this.
- The model returns 10 paths while tasks have 2 to 8 labels, which bounds precision and F1; compare conditions to each other, not to 1.0.
- Labels from the Git diff include change-log files that say little about code impact.
- Jira shows the current issue text, which may have been edited after the fix.
- Baseline seed files are often wrong.
- Why more context did not help (for example distraction of a small model, or anchoring on shown files) has not been tested.

## Repository layout

- `cia/`: data handling, context construction (`analysis.py`), providers, experiment execution, prompt-size guards (`guards.py`)
- `config/experiment.toml`: model and experiment settings
- `data/`: task manifest, schema, drafts
- `scripts/`: batch summary, lenient re-score, task screening, sampling, text review, token measurement
- `results/`: summaries and screening output
- `runs/`: committed run artifacts
- `docs/`: model information and the pilot task audit
- `tests/`: unit tests

---

## Milestone 2 pilot README (original, preserved)

> The section below is the README as it stood for Milestone 2. It is kept unchanged so the whole project history is in one place. Where it says C1-C3 are "planned", that was true then; they were run in Milestone 3 (see above).

A reproducible pilot for ranking Java files that may be affected by a software maintenance request. The current pilot uses one verified Apache Ivy task, **IVY-1028**. Its results are an initial one-task observation, not evidence of general model performance.

### Project status

- The task manifest, data validation, analysis pipeline, experiment configuration, audit, and unit tests are included in this repository.
- Two inspectable pilot attempts are committed under [`runs/`](runs/):
  - [Original C0 attempt](runs/final_c0_attempt/)
  - [Constrained C0 attempt](runs/final_constrained_attempt/)
- The constrained C0 model call completed successfully. The original C0 attempt was rejected during ranked-path validation because some predicted paths did not exist at the parent revision. Both outcomes are retained as part of the pilot record.
- C1–C3 are described as planned context conditions; do not interpret them as completed evaluations based on these artifacts alone.

### Requirements

- Python 3.11 or newer
- Git available on `PATH`
- A local clone of Apache Ivy containing the target and parent commits listed below
- Ollama with `qwen2.5-coder:7b` for the local LLM run

The analysis and unit tests use the Python standard library. The tests and offline demonstration do not require internet access, Ollama, or an API key.

### Setup and commands

Run from the repository root in PowerShell:

```powershell
python -m pip install -e .
python -m unittest discover -s tests -v
python -m cia validate-manifest data/tasks.jsonl
python -m cia run-task --help
```

Run the C0 pilot:

```powershell
python -m cia run-task --task-id ripple-ant-ivy-IVY-1028 --repository "C:\path\to\ant-ivy"
```

Run the constrained prompt condition for the same task:

```powershell
python -m cia run-task --task-id ripple-ant-ivy-IVY-1028 --repository "C:\path\to\ant-ivy" --condition C0_CONSTRAINED
```

Replace the example path with the path to your local Apache Ivy clone. The command validates issue chronology, commit ancestry, and the parent-to-target Git diff path set before constructing predictor input. It writes prompt and context artifacts, baseline rankings, model output, and metrics when the model output passes ranked-path validation.

### Task and data provenance

- **Task:** Ripple record `instance-00010`, used for candidate discovery and cross-checking; the evaluation labels come from the exact target patch, not Ripple's impact-set-files metadata.
- **Issue:** [Apache Ivy IVY-1028](https://issues.apache.org/jira/browse/IVY-1028)
- **Source repository:** [Apache Ivy](https://github.com/apache/ant-ivy)
- **Target commit:** `67647ddcf1c42762dd7bc6df83ba951edad1ce93`
- **Parent commit:** `e556b3cdeb75a6ed2285f581164d76f743ab85ee`
- **Reference changed paths:** `CHANGES.txt` and `src/java/org/apache/ivy/plugins/resolver/IBiblioResolver.java`

The task manifest at [`data/tasks.jsonl`](data/tasks.jsonl) records source provenance, revision identifiers, and cleaning decisions. The task audit is available at [`docs/task-audit-ripple-ant-ivy-ivy-1028.md`](docs/task-audit-ripple-ant-ivy-ivy-1028.md). The target diff, commit message, changed-path labels, and post-target repository content are excluded from predictor input.

### Conditions and baselines

- **C0:** cleaned issue text and the file tree at the parent revision.
- **C0_CONSTRAINED:** cleaned issue text and a candidate-path list selected from the parent tree. This is a prompt-level constraint, not constrained decoding; output paths are still validated after generation.
- **C1 (planned):** C0 plus a seed and retrieved Java source.
- **C2 (planned):** C1 plus dependency information.
- **C3 (planned):** C2 plus relevant tests, documentation, and parent-bounded co-change history.

Dependency and historical co-change baselines use a deterministic seed selected from the issue and parent tree. The local Ollama provider is used for this pilot. An OpenAI-compatible provider is available in the code but is disabled and was not called for these runs.

The model configuration is recorded in [`config/experiment.toml`](config/experiment.toml). The pilot uses `qwen2.5-coder:7b` through Ollama with temperature `0`, seed `42`, top-p `1.0`, top-k `40`, repeat penalty `1.0`, context length `32768`, and a maximum of `2048` generated tokens. The run JSONs record the model digest, prompt hash, token counts, latency, settings, predictions, and metrics.

### Inspectable pilot observations

#### Constrained C0

The committed [constrained C0 result](runs/final_constrained_attempt/20261025T195633.620379Z_C0_CONSTRAINED_pilot.json) records:

| Metric | Value |
|---|---:|
| Precision | 0.10 |
| Recall | 0.50 |
| F1 | 0.1667 |
| Recall@5 | 0.50 |
| Recall@10 | 0.50 |
| Input / output tokens | 1,731 / 615 |
| Latency | about 22.65 seconds |

The task has two reference changed paths, including the non-Java file `CHANGES.txt`, while candidate prediction is focused on Java paths. This creates a recall ceiling of 0.50 for this condition under the current candidate scope. Treat this as a data/candidate-scope limitation to address in the next milestone, not as a general performance claim.

#### Original C0 validation failure

The [original C0 result](runs/final_c0_attempt/20261025T190022.151353Z_C0_pilot.json) records a failed validation: four of ten predicted paths were absent from the parent revision. Because the ranked paths did not pass validation, the attempt is not treated as a valid model score. Keeping this artifact makes the failure inspectable and documents why path validation matters.

The deterministic baselines are recorded in both pilot JSON files. In the constrained C0 artifact, the dependency baseline has precision, recall, and F1 of 0.0; the historical co-change baseline has precision 0.10, recall 0.50, and F1 approximately 0.1667. These are observations on this single task only.

### Experiment artifacts

Selected pilot outputs are versioned in the repository for inspection and reproducibility. The folders contain each attempt's context manifest, prompt, and pilot-result JSON:

- [All run artifacts](runs/)
- [Original C0 artifacts](runs/final_c0_attempt/)
- [Constrained C0 artifacts](runs/final_constrained_attempt/)

Generated outputs from future runs may remain local unless deliberately added to version control. Before publishing additional artifacts, check that they contain no secrets, credentials, or private data.

### Limitations and next steps

- One task and one successful constrained model call are pilot evidence, not a conclusive evaluation.
- Patch-changed paths are an imperfect proxy for all files an issue might affect.
- The candidate scope currently excludes non-Java paths, limiting recall for this task.
- C0 can generate paths absent from the parent revision; ranked-path validation rejects those outputs.
- The issue cleaning decisions and label construction are documented in the task manifest and audit.
- The next milestone should address candidate-scope coverage and evaluate the planned context conditions before drawing comparisons between them.

### Repository layout

- `cia/`: data handling, context construction, providers, experiment execution, and analysis
- `config/experiment.toml`: model and experiment settings
- `data/tasks.jsonl`: task manifest
- `data/task.schema.json`: task-manifest schema
- `docs/task-audit-ripple-ant-ivy-ivy-1028.md`: selected-task audit
- `runs/`: committed pilot artifacts
- `tests/`: unit tests

