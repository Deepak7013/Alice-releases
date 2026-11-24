"""Bounded natural pause and long-sentence chunk planning for ALICE speech."""
from __future__ import annotations
import re

_ABBREVIATIONS = ("Mr.", "Mrs.", "Ms.", "Dr.", "Prof.", "Sr.", "Jr.", "St.", "vs.", "etc.", "e.g.", "i.e.", "No.", "Fig.")
_SENTINEL = "\u0000"

def _protect_nonterminal_periods(text: str) -> str:
    protected = re.sub(r"(?<=\d)\.(?=\d)", _SENTINEL, text)
    for abbreviation in _ABBREVIATIONS:
        pattern = re.compile(r"(?<!\w)" + re.escape(abbreviation), re.IGNORECASE)
        protected = pattern.sub(lambda m: m.group(0).replace(".", _SENTINEL), protected)
    return protected

def _split_long_part(part: str, max_chars: int) -> list[str]:
    remaining = part.strip()
    chunks: list[str] = []
    while len(remaining) > max_chars:
        window = remaining[:max_chars + 1]
        # Prefer natural clause boundaries, then a word boundary, never an empty chunk.
        cut = max(window.rfind(mark) for mark in (",", ";", ":"))
        if cut < max_chars // 3:
            cut = window.rfind(" ")
        if cut <= 0:
            cut = max_chars
        else:
            cut += 1 if window[cut] in ",;:" else 0
        piece = remaining[:cut].strip()
        if not piece:
            cut = max_chars
            piece = remaining[:cut].strip()
        chunks.append(piece)
        remaining = remaining[cut:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks

def plan_natural_pauses(text: object, *, max_chars: int = 240) -> list[dict[str, object]]:
    """Split on sentence boundaries and bound chunk length for low-latency streaming."""
    if isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars < 20:
        raise ValueError("max_chars_must_be_integer_at_least_20")
    clean = str(text or "").strip()
    if not clean:
        return []
    protected = _protect_nonterminal_periods(clean)
    sentences = re.split(r"(?<=[.!?])\s+", protected)
    result: list[dict[str, object]] = []
    for sentence in sentences:
        sentence = sentence.replace(_SENTINEL, ".").strip()
        if not sentence:
            continue
        for part in _split_long_part(sentence, max_chars):
            pause_ms = 220
            if part.endswith(("?", "!")):
                pause_ms = 300
            elif part.endswith((",", ";", ":")) or "," in part or ";" in part:
                pause_ms = 180
            result.append({"text": part, "pause_ms": pause_ms})
    return result
