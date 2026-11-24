
"""Safety filters for knowledge ingestion.

Knowledge is data, not authority. This module intentionally errs on the side
of rejecting likely credentials and instruction-like permission escalation.
"""
from __future__ import annotations
import re

SECRET_PATTERNS = [
    re.compile(r"(?i)\b(api[\s_-]?key|access[\s_-]?token|refresh[\s_-]?token|password|passwd|secret|authorization)\b\s*[:=]\s*\S+"),
    # Google AI Studio API keys can be pasted without a label. Catch the
    # recognizable prefix before a prompt is shown, persisted, or transmitted.
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"(?i)\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b"),
]

# These phrases are not automatically dangerous, but should never be treated
# as capability/permission grants merely because a document contains them.
AUTHORITY_PATTERNS = [
    re.compile(r"(?i)\bgrant\s+(?:yourself|itself|alice)\b"),
    re.compile(r"(?i)\bdisable\s+(?:the\s+)?safety\b"),
    re.compile(r"(?i)\bbypass\s+(?:the\s+)?permission\b"),
    re.compile(r"(?i)\bignore\s+(?:all\s+)?(?:safety|security)\b"),
]


def redact_secrets(text: str) -> tuple[str, bool]:
    value = str(text)
    found = False
    for pattern in SECRET_PATTERNS:
        value, n = pattern.subn("[REDACTED_SECRET]", value)
        found = found or bool(n)
    return value, found


def contains_authority_instructions(text: str) -> bool:
    return any(p.search(text) for p in AUTHORITY_PATTERNS)


def sanitize(text: str) -> tuple[str, bool, bool]:
    cleaned, redacted = redact_secrets(text)
    return cleaned, redacted, contains_authority_instructions(cleaned)
