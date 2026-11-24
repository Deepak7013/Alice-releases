"""Deterministic voice/text synchronization gate for ALICE responses."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class DeliverySyncDecision:
    display_text: str
    voice_text: str
    speak: bool
    synchronized: bool
    reason: str


def synchronize_response(display_text: object, *, voice_enabled: bool = True) -> DeliverySyncDecision:
    """Ensure voice receives exactly the canonical text displayed to the user."""
    text = str(display_text if display_text is not None else "").strip()
    if not text:
        return DeliverySyncDecision("", "", False, True, "empty_response_no_speech")
    if not voice_enabled:
        return DeliverySyncDecision(text, "", False, True, "voice_disabled")
    return DeliverySyncDecision(text, text, True, True, "ui_voice_synchronized")
