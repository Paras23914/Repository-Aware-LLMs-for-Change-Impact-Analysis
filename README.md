# Repository-Aware Change Impact Analysis

A reproducible pilot for ranking Java files that may be affected by a software maintenance request. The current pilot uses one verified Apache Ivy task, **IVY-1028**. Its results are an initial one-task observation, not evidence of general model performance.

## Project status

- The task manifest, data validation, analysis pipeline, experiment configuration, audit, and unit tests are included in this repository.
- Two inspectable pilot attempts are committed under [`runs/`](runs/):
  - [Original C0 attempt](runs/final_c0_attempt/)
  - [Constrained C0 attempt](runs/final_constrained_attempt/)
- The constrained C0 model call completed successfully. The original C0 attempt was rejected during ranked-path validation because some predicted paths did not exist at the parent revision. Both outcomes are retained as part of the pilot record.
- C1–C3 are described as planned context conditions; do not interpret them as completed evaluations based on these artifacts alone.

## Requirements

- Python 3.11 or newer
- Git available on `PATH`
- A local clone of Apache Ivy containing the target and parent commits listed below
- Ollama with `qwen2.5-coder:7b` for the local LLM run

The analysis and unit tests use the Python standard library. The tests and offline demonstration do not require internet access, Ollama, or an API key.

## Setup and commands

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

## Task and data provenance

- **Task:** Ripple record `instance-00010`, used for candidate discovery and cross-checking; the evaluation labels come from the exact target patch, not Ripple's impact-set-files metadata.
- **Issue:** [Apache Ivy IVY-1028](https://issues.apache.org/jira/browse/IVY-1028)
- **Source repository:** [Apache Ivy](https://github.com/apache/ant-ivy)
- **Target commit:** `67647ddcf1c42762dd7bc6df83ba951edad1ce93`
- **Parent commit:** `e556b3cdeb75a6ed2285f581164d76f743ab85ee`
- **Reference changed paths:** `CHANGES.txt` and `src/java/org/apache/ivy/plugins/resolver/IBiblioResolver.java`

The task manifest at [`data/tasks.jsonl`](data/tasks.jsonl) records source provenance, revision identifiers, and cleaning decisions. The task audit is available at [`docs/task-audit-ripple-ant-ivy-ivy-1028.md`](docs/task-audit-ripple-ant-ivy-ivy-1028.md). The target diff, commit message, changed-path labels, and post-target repository content are excluded from predictor input.

## Conditions and baselines

- **C0:** cleaned issue text and the file tree at the parent revision.
- **C0_CONSTRAINED:** cleaned issue text and a candidate-path list selected from the parent tree. This is a prompt-level constraint, not constrained decoding; output paths are still validated after generation.
- **C1 (planned):** C0 plus a seed and retrieved Java source.
- **C2 (planned):** C1 plus dependency information.
- **C3 (planned):** C2 plus relevant tests, documentation, and parent-bounded co-change history.

Dependency and historical co-change baselines use a deterministic seed selected from the issue and parent tree. The local Ollama provider is used for this pilot. An OpenAI-compatible provider is available in the code but is disabled and was not called for these runs.

The model configuration is recorded in [`config/experiment.toml`](config/experiment.toml). The pilot uses `qwen2.5-coder:7b` through Ollama with temperature `0`, seed `42`, top-p `1.0`, top-k `40`, repeat penalty `1.0`, context length `32768`, and a maximum of `2048` generated tokens. The run JSONs record the model digest, prompt hash, token counts, latency, settings, predictions, and metrics.

## Inspectable pilot observations

### Constrained C0

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

### Original C0 validation failure

The [original C0 result](runs/final_c0_attempt/20261025T190022.151353Z_C0_pilot.json) records a failed validation: four of ten predicted paths were absent from the parent revision. Because the ranked paths did not pass validation, the attempt is not treated as a valid model score. Keeping this artifact makes the failure inspectable and documents why path validation matters.

The deterministic baselines are recorded in both pilot JSON files. In the constrained C0 artifact, the dependency baseline has precision, recall, and F1 of 0.0; the historical co-change baseline has precision 0.10, recall 0.50, and F1 approximately 0.1667. These are observations on this single task only.

## Experiment artifacts

Selected pilot outputs are versioned in the repository for inspection and reproducibility. The folders contain each attempt's context manifest, prompt, and pilot-result JSON:

- [All run artifacts](runs/)
- [Original C0 artifacts](runs/final_c0_attempt/)
- [Constrained C0 artifacts](runs/final_constrained_attempt/)

Generated outputs from future runs may remain local unless deliberately added to version control. Before publishing additional artifacts, check that they contain no secrets, credentials, or private data.

## Limitations and next steps

- One task and one successful constrained model call are pilot evidence, not a conclusive evaluation.
- Patch-changed paths are an imperfect proxy for all files an issue might affect.
- The candidate scope currently excludes non-Java paths, limiting recall for this task.
- C0 can generate paths absent from the parent revision; ranked-path validation rejects those outputs.
- The issue cleaning decisions and label construction are documented in the task manifest and audit.
- The next milestone should address candidate-scope coverage and evaluate the planned context conditions before drawing comparisons between them.

## Repository layout

- `cia/`: data handling, context construction, providers, experiment execution, and analysis
- `config/experiment.toml`: model and experiment settings
- `data/tasks.jsonl`: task manifest
- `data/task.schema.json`: task-manifest schema
- `docs/task-audit-ripple-ant-ivy-ivy-1028.md`: selected-task audit
- `runs/`: committed pilot artifacts
- `tests/`: unit tests
