# Local model and cloud endpoint setup plan

**Status: awaiting approval; no runtime or model has been installed or
downloaded.** Prepared 2026-10-25.

## Machine constraints observed

- NVIDIA GeForce RTX 4060 Laptop GPU: 8,188 MiB total VRAM.
- Physical system RAM: 15.6 GiB total, 1.3 GiB available at inspection time.
- Qwen3.8-27B is a 27B-parameter model. At 4-bit, the weight payload alone has
  a theoretical lower bound of about 12.6 GiB, before quantization metadata,
  runtime allocations, and context/KV memory. This cannot fit in the current
  GPU and exceeds currently available system RAM.
- The `ollama` command was present, but its model-list check returned no model
  listing output. No local inference endpoint variables were configured.

The Qwen model card names Transformers, vLLM, and SGLang as serving options and
shows an OpenAI-compatible vLLM endpoint. That does not establish that any of
those runtimes is installed or that the 27B model will fit this laptop.

## Recommended path

1. Keep this laptop unchanged. Do not download weights or change system
   settings.
2. Identify a local inference host that already has sufficient GPU or system
   memory for Qwen3.8-27B and a supported serving runtime. The model remains
   local to that host; expose its OpenAI-compatible endpoint only to the
   research machine as needed.
3. Record the exact model revision, quantization/precision, runtime version,
   context limit, and serving command in experiment configuration.
4. Set `CIA_LOCAL_BASE_URL` and `CIA_LOCAL_MODEL` in the process environment.
   Do not store tokens in source files. Configure `CIA_LOCAL_API_KEY` only if
   the local server requires it.
5. Run a single non-study smoke request, inspect the server-reported model ID
   and available token usage, then run the reviewed real task only after its
   issue timestamp and label policy are resolved.

If no suitable local host is available, the alternative is to assess a
quantized CPU/GPU-offload setup on this laptop. That is a separate experiment:
it requires selecting a specific conversion, checking its model compatibility
and quality tradeoff, confirming free disk/RAM, and estimating runtime. It may
be infeasible at the current 1.3 GiB available RAM. I will not proceed with
that path without a separately approved package/model plan.

## Cloud endpoint

The project has a separate OpenAI-compatible cloud adapter. The cloud endpoint
is not yet configured because the provider response did not include a base URL
or exact model ID. Set `CIA_CLOUD_BASE_URL`, `CIA_CLOUD_MODEL`, and
`CIA_CLOUD_API_KEY` in the process environment after selecting a provider. The
key must not be committed or pasted into source files. No cloud request has
been made.

## Approval needed to continue

- Provide an existing local host's base URL and exact served model ID, or
  approve a specific quantized local setup after reviewing its artifact size,
  runtime, compatibility evidence, and expected quality tradeoff.
- Provide the cloud endpoint base URL and exact model ID. Configure the secret
  locally as `CIA_CLOUD_API_KEY`.

