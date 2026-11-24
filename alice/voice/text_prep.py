"""Deterministic text preparation for ALICE's local speech pipeline."""
from __future__ import annotations
import json
import re
from pathlib import Path

_URL = re.compile(r"https?://\S+|www\.\S+", re.I)
_MARKDOWN = re.compile(r"(```.*?```|`[^`]*`|\*\*|__|~~|\*|_)", re.S)
_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]"
)
_SPACE = re.compile(r"\s+")


def prepare_for_speech(text: object) -> str:
    """Remove presentation markup and literal emoji symbols without speaking labels."""
    value = str(text if text is not None else "")
    value = _URL.sub("", value)
    value = _MARKDOWN.sub("", value)
    value = _EMOJI.sub("", value)
    return _SPACE.sub(" ", value).strip()


def apply_pronunciation(text: object, dictionary: dict[str, str] | None = None) -> str:
    """Apply bounded literal word/phrase hints without changing canonical text."""
    value = prepare_for_speech(text)
    if not isinstance(dictionary, dict):
        return value
    entries = []
    for source, spoken in list(dictionary.items())[:200]:
        if not isinstance(source, str) or not isinstance(spoken, str):
            continue
        source, spoken = source.strip(), spoken.strip()
        if not source or not spoken or len(source) > 100 or len(spoken) > 200:
            continue
        if any(ord(ch) < 32 and ch not in "\t" for ch in source + spoken):
            continue
        entries.append((source, spoken))
    for source, spoken in sorted(entries, key=lambda item: len(item[0]), reverse=True):
        value = re.sub(rf"(?<!\w){re.escape(source)}(?!\w)", lambda _match, replacement=spoken: replacement, value, flags=re.I)
    return value


def load_pronunciation_dictionary(path: str | Path) -> dict[str, str]:
    """Load a bounded, data-only pronunciation map; invalid files fail closed.

    The file may contain a direct mapping or {"pronunciations": {...}}.
    Values are plain text only; no code, regex, or executable templates are loaded.
    """
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    if "pronunciations" in payload:
        payload = payload.get("pronunciations")
    if not isinstance(payload, dict):
        return {}
    result: dict[str, str] = {}
    for source, spoken in list(payload.items())[:200]:
        if not isinstance(source, str) or not isinstance(spoken, str):
            continue
        source = source.strip()
        spoken = spoken.strip()
        if not source or not spoken or len(source) > 100 or len(spoken) > 200:
            continue
        if any(ord(ch) < 32 and ch not in "\t" for ch in source + spoken):
            continue
        result[source] = spoken
    return result
