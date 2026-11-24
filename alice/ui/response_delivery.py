"""Canonical response delivery planning for ALICE UI and voice output."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ResponseDelivery:
    text: str
    voice_text: str
    status: str
    valid: bool
    reason: str


def canonicalize_response(result: object) -> ResponseDelivery:
    """Produce one canonical response string for both UI and optional voice.

    The function is side-effect-free and never calls TTS. A missing provider
    response becomes an explicit error message rather than an empty payload.
    """
    if isinstance(result, dict):
        status = str(result.get("status", "unknown"))
        if status == "completed":
            text = str(result.get("result", "") or "").strip()
        elif status == "failed":
            text = "Error: " + str(result.get("error", "Unknown error") or "Unknown error").strip()
        elif status == "awaiting_approval":
            approval = result.get("approval", {}) or {}
            text = (
                "I need your approval before doing this.\nReason: "
                + str(approval.get("reason", "Consequential action requires confirmation.") or "Consequential action requires confirmation.").strip()
            )
        else:
            text = str(result).strip()
    else:
        status = "completed"
        text = str(result if result is not None else "").strip()
    if not text:
        text = "I received an empty response and could not produce a usable answer."
        return ResponseDelivery(text, "", status, False, "empty_response_replaced")
    return ResponseDelivery(text, text, status, True, "canonical_response_ready")
