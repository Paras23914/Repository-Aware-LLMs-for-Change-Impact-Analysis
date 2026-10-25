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

Run from the repository root in PowerShell:

~~~powershell
python -m pip install -e .
python -m unittest discover -s tests -v
python -m cia validate-manifest data/tasks.jsonl
python -m cia run-task --help
~~~

Run the local one-task C0 pilot:

~~~powershell
python -m cia run-task --task-id ripple-ant-ivy-IVY-1028 --repository "C:\path\to\ant-ivy"
~~~

Run the constrained prompt condition with the same validated task:

~~~powershell
python -m cia run-task --task-id ripple-ant-ivy-IVY-1028 --repository "C:\path\to\ant-ivy" --condition C0_CONSTRAINED
~~~

The command validates issue chronology, fixed commits, first parent, and the
full Git diff path set before building predictor input. It writes prompt and
context artifacts, baseline rankings, the model outcome, and metrics (if the
model output passes ranked-path validation) under `runs/real_task_pilot/`.
Run artifacts are local and ignored by Git; preserve them when archiving results.

## Workflow

The manifest in `data/tasks.jsonl` records source URLs, issue text provenance,
fixed SHAs, cleaning decisions, and patch-path labels. The selected-task audit
is in `docs/task-audit-ripple-ant-ivy-ivy-1028.md`. The parent-revision reader
keeps the target patch and labels out of model input.

- C0: issue text and parent-revision file tree
- C0_CONSTRAINED: issue text and a candidate-path list selected from the
  parent-revision tree. This is a prompt constraint, not a hard decoding
  constraint; invalid paths are still rejected during validation.
- C1: C0 plus seed and retrieved Java source
- C2: C1 plus dependency information
- C3: C2 plus relevant tests, documentation, and parent-bounded co-change history

Dependency and historical co-change baselines use a deterministic seed chosen
from the issue and parent tree. The Ollama provider is local. A separate
OpenAI-compatible provider remains available but is not configured or called
by this pilot.

## Limitations

The reference labels are files changed by the patch, not a complete oracle of
all files an issue could affect. A single task and model call are pilot evidence,
not conclusive evidence of general performance. Model results are reported only
when ranked-path validation succeeds. The experiment's issue cleaning decisions
are recorded in the task manifest.
