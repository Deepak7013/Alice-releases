"""Bounded desktop scroll wrapper requiring a fresh accessible-text transition."""
from __future__ import annotations

import hashlib


def _digest(value: str) -> str:
    return hashlib.sha256(value.casefold().encode("utf-8")).hexdigest()


def scroll_with_expected_text(controller, observer, amount, expected_text: str):
    """Scroll a bounded number of notches only when expected text is initially absent."""
    expected = str(expected_text or "").strip()
    try:
        steps = int(amount)
    except (TypeError, ValueError, OverflowError):
        return {"ok": False, "error": "invalid_desktop_scroll_amount"}
    if (isinstance(amount, bool) or str(steps) != str(amount).strip()
            or steps == 0 or abs(steps) > 20 or not expected or len(expected) > 256):
        return {"ok": False, "error": "invalid_verified_desktop_scroll_request"}
    try:
        before = observer.visible_texts()
        if not isinstance(before, list):
            return {"ok": False, "error": "desktop_observer_invalid_result"}
        if any(expected.casefold() in str(value).casefold() for value in before):
            return {"ok": False, "error": "expected_text_already_visible"}
        controller.scroll(steps)
        return {"ok": True, "action": "desktop_scroll_verified", "amount": steps,
                "_postcondition_context": {"expected_absent_before": True,
                    "expected_text_sha256": _digest(expected)}}
    except Exception as exc:
        return {"ok": False, "error": f"desktop_scroll_observation_failed:{type(exc).__name__}"}


def verify_verified_desktop_scroll(observer, args, result):
    """Verify a new expected accessible text is present after the scroll action."""
    from ..execution.postconditions import PostconditionResult
    args = args if isinstance(args, dict) else {}
    expected = str(args.get("expected_text") or "").strip()
    context = result.get("_postcondition_context") if isinstance(result, dict) else None
    try:
        amount = int(args.get("amount"))
    except (TypeError, ValueError, OverflowError):
        amount = 0
    valid = (bool(expected) and len(expected) <= 256 and amount != 0 and abs(amount) <= 20
             and isinstance(result, dict) and result.get("ok") is True
             and result.get("action") == "desktop_scroll_verified"
             and result.get("amount") == amount
             and isinstance(context, dict) and context.get("expected_absent_before") is True
             and context.get("expected_text_sha256") == _digest(expected))
    if not valid:
        return PostconditionResult(False, {"observed": False}, "desktop_scroll_binding_invalid")
    try:
        names = observer.visible_texts()
        if not isinstance(names, list):
            raise TypeError("invalid UI Automation observation")
        found = any(expected.casefold() in str(value).casefold() for value in names)
    except Exception as exc:
        return PostconditionResult(False, {"observed": False}, f"desktop_scroll_readback_failed:{type(exc).__name__}")
    evidence = {"observed": True, "expected_text_visible": found,
                "expected_text_sha256": _digest(expected), "scroll_amount": amount}
    return PostconditionResult(found, evidence,
        "desktop_scroll_transition_observed" if found else "desktop_scroll_transition_not_observed")
