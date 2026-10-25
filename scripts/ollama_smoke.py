"""One-request, synthetic-only Ollama smoke check using the existing pipeline."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import tomllib
from dataclasses import asdict
from pathlib import Path

from cia.context import build_c0
from cia.providers import OllamaConfig, OllamaProvider
from cia.repository import RepositorySnapshot
from cia.runner import run_prediction
from cia.tasks import PredictorInput


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _git(root: Path, *args: str) -> str:
    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": "CIA synthetic Ollama smoke",
        "GIT_AUTHOR_EMAIL": "cia-smoke@example.invalid",
        "GIT_COMMITTER_NAME": "CIA synthetic Ollama smoke",
        "GIT_COMMITTER_EMAIL": "cia-smoke@example.invalid",
        "GIT_AUTHOR_DATE": "2020-01-01T00:00:00Z",
        "GIT_COMMITTER_DATE": "2020-01-01T00:00:00Z",
    })
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True,
        encoding="utf-8", env=env, check=False,
    )
    if result.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def main() -> int:
    config = tomllib.loads((PROJECT_ROOT / "config" / "experiment.toml").read_text(encoding="utf-8"))
    model = config["models"]["local"]
    if not model.get("enabled") or model.get("provider") != "ollama":
        raise RuntimeError("local provider is not enabled as Ollama in config/experiment.toml")
    ollama_config = OllamaConfig(
        model_tag=model["model_tag"],
        base_url=model["base_url"],
        timeout_seconds=float(model["timeout_seconds"]),
        num_ctx=int(model["num_ctx"]),
        seed=int(model["seed"]),
        top_p=float(model["top_p"]),
        top_k=int(model["top_k"]),
        repeat_penalty=float(model["repeat_penalty"]),
        response_format=model["response_format"],
    )
    generation = int(model["num_predict"])

    with tempfile.TemporaryDirectory(prefix="cia-ollama-smoke-", dir=PROJECT_ROOT) as tmp:
        root = Path(tmp) / "synthetic-repo"
        root.mkdir()
        _git(root, "init", "-q")
        main_src = root / "src/main/java/example"
        main_src.mkdir(parents=True)
        (main_src / "QuoteCalculator.java").write_text(
            "package example;\npublic class QuoteCalculator { int total() { return 10; } }\n",
            encoding="utf-8",
        )
        (main_src / "QuoteFormatter.java").write_text(
            "package example;\npublic class QuoteFormatter { String format(int amount) { return \"\" + amount; } }\n",
            encoding="utf-8",
        )
        _git(root, "add", "--all")
        _git(root, "commit", "-m", "synthetic smoke fixture")
        parent_sha = _git(root, "rev-parse", "HEAD")
        repository = RepositorySnapshot.at_commit(root, parent_sha)
        predictor_input = PredictorInput(
            issue_text="For this synthetic output-format smoke check, identify the Java file most relevant to changing the quote total calculation.",
            repository=repository,
        )
        context = build_c0(predictor_input)
        result = run_prediction(
            task_id="synthetic-ollama-smoke",
            context=context,
            provider=OllamaProvider(ollama_config),
            temperature=float(model["temperature"]),
            max_output_tokens=generation,
            run_kind="synthetic-provider-smoke-only",
        )

        output_dir = PROJECT_ROOT / "runs" / "ollama_smoke"
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = result.run_started_at.replace(":", "").replace("-", "")
        artifact_path = output_dir / f"{stamp}_{result.prompt_sha256[:8]}.json"
        prompt_path = output_dir / f"{stamp}_{result.prompt_sha256[:8]}_prompt.txt"
        manifest_path = output_dir / f"{stamp}_{result.prompt_sha256[:8]}_context.json"
        prompt_path.write_text(context.text, encoding="utf-8")
        manifest = {
            "artifact_type": "synthetic-ollama-smoke-only",
            "is_research_evidence": False,
            "task_id": result.task_id,
            "condition": context.condition,
            "source_commit": parent_sha,
            "prompt_file": prompt_path.name,
            "prompt_sha256": result.prompt_sha256,
            "items": [asdict(item) for item in context.items],
            "target_sha": None,
            "reference_paths": None,
            "metrics": None,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        artifact = {
            "artifact_type": "synthetic-ollama-smoke-only",
            "is_research_evidence": False,
            "context_manifest": manifest_path.name,
            "run": result.to_dict(),
        }
        artifact_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"status={result.status}")
    print(f"provider={result.provider_name}")
    print(f"model_tag={result.model_id}")
    print(f"model_digest={result.model_digest}")
    print(f"condition={result.condition}")
    print(f"latency_ms={result.latency_ms:.3f}")
    print(f"input_tokens={result.input_tokens}")
    print(f"output_tokens={result.output_tokens}")
    for index, prediction in enumerate(result.predictions, start=1):
        print(f"prediction_{index}={prediction.path}\t{prediction.rationale}")
    if result.error:
        print(f"error={result.error}")
    print(f"artifact={artifact_path}")
    return 0 if result.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

