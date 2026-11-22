"""One-request feasibility probe for the Groq free tier (no project code touched).

Usage (key must be in the environment, never on the command line):
    python scripts/groq_probe.py PROMPT_FILE [--model openai/gpt-oss-120b] [--max-tokens 1500] [--json]

It sends the saved prompt file as a single user message and prints: HTTP status,
the token counts Groq reports, the rate-limit headers, the latency, and the first
300 characters of the reply. It does not print the API key.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

URL = "https://api.groq.com/openai/v1/chat/completions"
HEADERS_OF_INTEREST = (
    "x-ratelimit-limit-tokens", "x-ratelimit-remaining-tokens", "x-ratelimit-reset-tokens",
    "x-ratelimit-limit-requests", "x-ratelimit-remaining-requests", "retry-after",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt_file")
    parser.add_argument("--model", default="openai/gpt-oss-120b")
    parser.add_argument("--max-tokens", type=int, default=1500)
    parser.add_argument("--json", action="store_true", help="ask for JSON mode")
    args = parser.parse_args()

    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        print("Set GROQ_API_KEY in this terminal first (see instructions).", file=sys.stderr)
        return 2
    prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    payload = {
        "model": args.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": args.max_tokens,
        "stream": False,
    }
    if args.json:
        payload["response_format"] = {"type": "json_object"}

    request = Request(URL, data=json.dumps(payload).encode("utf-8"), method="POST",
                      headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                               "User-Agent": "cia-feasibility-probe/1.0"})
    print(f"prompt characters: {len(prompt)}; model: {args.model}; max_tokens: {args.max_tokens}; json: {args.json}")
    started = time.monotonic()
    try:
        with urlopen(request, timeout=120) as response:
            status = response.status
            headers = {k.lower(): v for k, v in response.headers.items()}
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        status = exc.code
        headers = {k.lower(): v for k, v in exc.headers.items()}
        body = {"error_body": exc.read(1500).decode("utf-8", errors="replace")}
    except URLError as exc:
        print(f"request failed: {exc}")
        return 1
    elapsed = time.monotonic() - started

    print(f"HTTP status: {status}; latency: {elapsed:.1f} s")
    for name in HEADERS_OF_INTEREST:
        if name in headers:
            print(f"  {name}: {headers[name]}")
    usage = body.get("usage") if isinstance(body, dict) else None
    if usage:
        print(f"  usage: prompt_tokens={usage.get('prompt_tokens')} completion_tokens={usage.get('completion_tokens')} total={usage.get('total_tokens')}")
    if "choices" in body:
        message = body["choices"][0].get("message", {})
        print("  finish_reason:", body["choices"][0].get("finish_reason"))
        print("  reply (first 300 chars):", (message.get("content") or "")[:300].replace("\n", " "))
    else:
        print("  error:", json.dumps(body)[:600])
    return 0 if status == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
