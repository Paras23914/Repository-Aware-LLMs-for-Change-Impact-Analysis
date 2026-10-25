# Repository-aware Change Impact Analysis

A reproducible, inspectable prototype for predicting Java files that may need
changes for a maintenance request. This is a new implementation; existing
workspace projects and archives are not used as implementation dependencies.

## Status

The offline pipeline, mock providers, and local Ollama adapter are implemented.
`data/tasks.jsonl` contains one provenance-checked Ant Ivy task (IVY-1028) for a
clearly labeled one-task pilot. Pilot artifacts record failed model outputs as
errors; only predictions that pass path validation receive metrics.

## Requirements

- Python 3.11 or later
- Git available on `PATH`
- No network access or model/API credentials are needed for the offline test

The core package uses only the Python standard library. Optional test tooling is
version-pinned in `pyproject.toml`; tests can also be run with `unittest`.

## Setup and commands

The deterministic core and tests use only Python's standard library. From this
directory in PowerShell:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

The deterministic synthetic-repository demonstration is:

```powershell
python -m unittest tests.test_offline_demo -v
```

The synthetic fixture is created in a temporary directory and removed by the
test runner. It contains no downloaded code or fabricated research task.

Validate a manifest without running a model:

```powershell
python -m cia validate-manifest data/tasks.jsonl
```

Build and save all four contexts for a validated manifest task:

```powershell
python -m cia build-contexts data/tasks.jsonl TASK_ID PATH_TO_LOCAL_REPOSITORY
```

## Model providers

`OllamaProvider` uses Ollama's native local HTTP API through Python's standard
library. Its base URL, exact model tag, context limit, seed, sampling settings,
output limit, and JSON response format are pinned in
`config/experiment.toml`. It records the digest reported by `/api/tags`, model
usage counts and durations when Ollama returns them, and wall-clock latency.

Run a one-request synthetic provider smoke check (not research evidence):

```powershell
$env:PYTHONPATH = "src"
python scripts/ollama_smoke.py
```

The smoke script uses the existing C0 context builder and runner, writes its
prompt manifest and run record under `runs/ollama_smoke/`, and reports no
research metrics. Unit tests use mocked HTTP responses and do not call Ollama.

Run the single real-task C0 pilot against a local Ant Ivy clone containing the
fixed revisions:

```powershell
$env:PYTHONPATH = "src"
python scripts/run_real_task.py --task-id ripple-ant-ivy-IVY-1028 --repository "C:\path\to\ant-ivy"
```

The pilot writes its C0 prompt, context manifest, baselines, provenance, and
model outcome under `runs/real_task_pilot/`. The model settings are pinned in
`config/experiment.toml`. This task is a one-task pilot and does not establish
general performance.

`OpenAICompatibleProvider` remains available for a separate cloud endpoint.
Its URL, model ID, and credential are not configured here. Set those through
the process environment variables in `.env.example`; the program does not
automatically load `.env` files. Unit tests do not require an API key.

## Data and leakage controls

Each accepted manifest row must identify its source, repository, issue text and
provenance, target commit, parent commit, changed-path reference labels, and
task-selection decision. Predictors receive a separate input type containing
only the issue and parent-revision repository view. The target commit and its
changed paths are retained for validation and scoring and are not passed to
predictors. Historical features must be derived only from commits reachable
from the parent commit.

See `data/task.schema.json` for the manifest contract. Do not add a task until
its issue text, timestamps, commit relationship, labels, and evaluation scope
have been checked and documented.

## Planned experiment conditions

- C0: request and parent-revision file tree
- C1: C0 plus seed and retrieved source
- C2: C1 plus dependency information
- C3: C2 plus relevant tests, documentation, and pre-parent co-change history

Every saved context manifest will list the source revision and included paths
and record why each item is allowed in its condition.

## Limitations

Changed files are an observed patch label, not a complete oracle for every file
that could be affected. Results depend on task provenance, issue-text quality,
repository availability, model/provider behavior, and context budgets. The
local Qwen2.5-Coder 7B Q4_K_M model is configured through Ollama. A valid ranked
prediction is not guaranteed: outputs are rejected if they contain malformed
JSON, duplicate paths, or paths absent from the parent tree.

