# Repository-Aware Change Impact Analysis

A small, reproducible pilot that ranks Java files likely to change for a
maintenance request. The pilot uses one verified Ant Ivy task (IVY-1028).
It reports changed-path metrics as a one-task observation, not general model
performance.

## Requirements

- Python 3.11+
- Git on PATH
- A local clone of Apache Ivy containing the fixed target and parent commits
- Ollama with qwen2.5-coder:7b for the model run

The analysis and tests use the Python standard library; unit tests and the
offline demonstration need no internet, Ollama, or API key.

## Setup and commands

Run from this directory in PowerShell:

~~~powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
python -m cia validate-manifest data/tasks.jsonl
python -m unittest discover -s tests -p test_analysis.py -v
python -m cia run-task --help
~~~

Run the local one-task C0 pilot:

~~~powershell
python -m cia run-task --task-id ripple-ant-ivy-IVY-1028 --repository "C:\path\to\ant-ivy"
~~~

The command validates the issue chronology, fixed commits, first parent, and
full Git diff path set before building the predictor input. It writes the C0
prompt, context manifest, baseline predictions, model outcome, and metrics
(if the model output passes ranked-path validation) under
runs/real_task_pilot/. Run artifacts are local and ignored by Git; preserve
them when archiving results.

## Workflow

The manifest in `data/tasks.jsonl` records source URLs, issue text provenance,
fixed SHAs, cleaning decisions, and patch-path labels. The selected-task audit
is in `docs/task-audit-ripple-ant-ivy-ivy-1028.md`. The parent-revision reader
keeps the target patch and labels out of model input.

- C0: issue text and parent-revision file tree
- C1: C0 plus seed and retrieved Java source
- C2: C1 plus dependency information
- C3: C2 plus relevant tests, documentation, and parent-bounded co-change history

Dependency and historical co-change baselines use a deterministic seed chosen
from the issue and parent tree. The Ollama provider is local. A separate
OpenAI-compatible provider remains available but is not configured or called
by this pilot.

## Limitations

The reference labels are files changed by the patch, not a complete oracle of
all files an issue could affect. Prior Qwen IVY-1028 attempts failed ranked-path
validation, so they have no model metrics. Existing run evidence is preserved
outside the Git submission in the sibling research archive and locally under
runs/real_task_pilot/.

