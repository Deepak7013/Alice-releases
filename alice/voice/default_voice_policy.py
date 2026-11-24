"""Deterministic default voice policy for ALICE Elysium.
Existing explicit user choices are preserved; fresh/blank settings default to Edge Aria.
"""
from __future__ import annotations
DEFAULT_LABEL = "Alice US – Aria"
DEFAULT_VOICE_ID = "en-US-AriaNeural"

def apply_default_voice(settings: dict | None) -> dict:
    """Return a copy with a safe default only when no voice was selected.

    Does not overwrite a non-empty saved voice id or label.
    """
    result = dict(settings) if isinstance(settings, dict) else {}
    # A saved SAPI choice is explicit even if neural_voice is blank. Do not
    # inject an Edge neural voice into that mode or rewrite its saved settings.
    if result.get("mode") in {"sapi", "fish_audio"}:
        return result
    voice_id = result.get("neural_voice")
    label = result.get("voice_name")
    if not isinstance(voice_id, str) or not voice_id.strip():
        result["neural_voice"] = DEFAULT_VOICE_ID
    if not isinstance(label, str) or not label.strip():
        result["voice_name"] = DEFAULT_LABEL
    result.setdefault("mode", "neural")
    result.setdefault("enabled", True)
    return result
