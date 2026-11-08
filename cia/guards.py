"""Prompt-size guards that stop silently clipped prompts from being scored.

Ollama (llama.cpp) does not fail when a prompt is longer than ``num_ctx``: it
drops part of the prompt and answers anyway. In this project's own measurement,
C1-C3 prompts of very different lengths (185K-235K characters) all reported
exactly 16,386 prompt tokens, i.e. about half of the 32,768-token window, with
11-14 characters per token against 3.4-4.2 for intact prompts. A clipped prompt
is not the context condition it claims to be, so such runs must be rejected.
"""

from __future__ import annotations

from cia.data import CIAError

# Conservative lower bound used BEFORE the call. Measured intact prompts were
# 3.4 (full tree, Java-heavy) to 4.2 (path list) characters per token.
PREFLIGHT_CHARS_PER_TOKEN = 3.0

# Upper bound used AFTER the call. Intact prompts stayed below 4.3; clipped
# prompts showed 11-14. Anything above this means tokens were dropped.
MAX_PLAUSIBLE_CHARS_PER_TOKEN = 6.0


class PromptTooLargeError(CIAError):
    """The prompt cannot fit the model window with room for the answer."""


def preflight_prompt_check(prompt_chars: int, num_ctx: int, max_output_tokens: int) -> None:
    """Refuse to send a prompt that would overflow the window (no model call made)."""
    limit_chars = int((num_ctx - max_output_tokens) * PREFLIGHT_CHARS_PER_TOKEN)
    if prompt_chars > limit_chars:
        raise PromptTooLargeError(
            f"prompt is {prompt_chars} characters; with num_ctx={num_ctx} and "
            f"{max_output_tokens} output tokens at most about {limit_chars} characters "
            "fit, so Ollama would silently clip it"
        )


def detect_truncation(prompt_chars: int, input_tokens: int | None, num_ctx: int) -> str | None:
    """Return a reason if the reported prompt tokens show the prompt was clipped."""
    if not input_tokens or input_tokens < 1:
        return None
    if input_tokens >= num_ctx - 16:
        return f"reported {input_tokens} prompt tokens, at the {num_ctx}-token window limit"
    ratio = prompt_chars / input_tokens
    if ratio > MAX_PLAUSIBLE_CHARS_PER_TOKEN:
        return (
            f"{prompt_chars} characters produced only {input_tokens} prompt tokens "
            f"({ratio:.1f} characters/token; intact prompts are about 3-4.5)"
        )
    return None
