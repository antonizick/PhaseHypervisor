"""Secret redaction applied to everything PHX writes to a log."""

import re
from typing import Any

REDACTED = "[REDACTED]"

# Each pattern keeps any leading label and replaces only the secret part.
_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-or-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
)
# NAME=value, NAME: value and the JSON forms "NAME": "value" and \"NAME\": \"value\" (a
# JSON string inside a stream-json line), for any upper-case name ending in a secret word
# (ANTHROPIC_AUTH_TOKEN, ANTHROPIC_API_KEY, OPENROUTER_API_KEY, GH_TOKEN, …). Quotes are
# kept, so a redacted JSON line stays valid JSON (Phase 11 audit).
_ASSIGNMENTS = re.compile(
    r"\b([A-Z][A-Z0-9_]*(?:TOKEN|API_KEY|SECRET|PASSWORD))"
    r"((?:\\?[\"'])?\s*[=:]\s*)"
    r"(\[REDACTED\]|\\\"(?:[^\"\\]|\\[^\"])*\\\"|\"(?:[^\"\\]|\\.)*\"|'[^']*'|[^\s,;}\]\"'\\]+)"
)
_BEARER = re.compile(r"(Authorization\s*:\s*Bearer\s+)[^\s\"'\\]+", re.IGNORECASE)


def _assignment(match: re.Match[str]) -> str:
    value = match.group(3)
    for quote in ('\\"', '"', "'"):
        if len(value) >= 2 * len(quote) and value.startswith(quote) and value.endswith(quote):
            return f"{match.group(1)}{match.group(2)}{quote}{REDACTED}{quote}"
    return f"{match.group(1)}{match.group(2)}{REDACTED}"


def redact_text(text: str) -> str:
    """Return ``text`` with known secret shapes replaced by ``[REDACTED]``."""
    text = _ASSIGNMENTS.sub(_assignment, text)
    text = _BEARER.sub(lambda m: f"{m.group(1)}{REDACTED}", text)
    for pattern in _PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


def redact(value: Any) -> Any:
    """Redact every string inside nested dicts, lists and tuples (keys included)."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {redact(k): redact(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    return value
