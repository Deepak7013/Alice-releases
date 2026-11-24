"""Bounded keyboard focus navigation verified by independent UI Automation readback."""
from __future__ import annotations

import hashlib


_VERIFIABLE_KEYS = frozenset({
    "enter", "escape", "space", "up", "down", "left", "right",
    "home", "end", "pageup", "pagedown",
})


def press_key_with_expected_text(controller, observer, key, expected_text: str):
    """Press one bounded navigation/activation key after checking a UIA baseline."""
    key_value = str(key or "").strip().casefold()
    expected = str(expected_text or "").strip()
    if key_value not in _VERIFIABLE_KEYS:
        return {"ok": False, "error": "unsupported_verified_desktop_key"}
    if not expected or len(expected) > 256:
        return {"ok": False, "error": "invalid_verified_desktop_key_request"}
    try:
        before = observer.visible_texts()
        if not isinstance(before, list):
            return {"ok": False, "error": "desktop_observer_invalid_result"}
        if any(expected.casefold() in str(value).casefold() for value in before):
            return {"ok": False, "error": "expected_text_already_visible"}
        controller.press(key_value)
        return {
            "ok": True,
            "action": "desktop_press_verified",
            "key": key_value,
            "_postcondition_context": {
                "expected_absent_before": True,
                "expected_text_sha256": hashlib.sha256(expected.casefold().encode("utf-8")).hexdigest(),
            },
        }
    except Exception as exc:
        return {"ok": False, "error": f"desktop_key_observation_failed:{type(exc).__name__}"}


def verify_verified_desktop_keypress(observer, args, result):
    """Require a fresh foreground UIA read to observe the requested new text."""
    from ..execution.postconditions import PostconditionResult

    args = args if isinstance(args, dict) else {}
    key_value = str(args.get("key") or "").strip().casefold()
    expected = str(args.get("expected_text") or "").strip()
    context = result.get("_postcondition_context") if isinstance(result, dict) else None
    expected_hash = hashlib.sha256(expected.casefold().encode("utf-8")).hexdigest() if expected else ""
    valid = (
        key_value in _VERIFIABLE_KEYS
        and bool(expected)
        and len(expected) <= 256
        and isinstance(result, dict)
        and result.get("ok") is True
        and result.get("action") == "desktop_press_verified"
        and result.get("key") == key_value
        and isinstance(context, dict)
        and context.get("expected_absent_before") is True
        and context.get("expected_text_sha256") == expected_hash
    )
    if not valid:
        return PostconditionResult(False, {"observed": False}, "desktop_keypress_binding_invalid")
    try:
        names = observer.visible_texts()
        if not isinstance(names, list):
            raise TypeError("invalid UI Automation observation")
        found = any(expected.casefold() in str(value).casefold() for value in names)
    except Exception as exc:
        return PostconditionResult(False, {"observed": False}, f"desktop_keypress_readback_failed:{type(exc).__name__}")
    evidence = {
        "observed": True,
        "expected_text_visible": found,
        "expected_text_sha256": expected_hash,
        "key": key_value,
    }
    return PostconditionResult(
        found,
        evidence,
        "desktop_keypress_transition_observed" if found else "desktop_keypress_transition_not_observed",
    )


def _focus_digest(snapshot):
    if not isinstance(snapshot, dict) or snapshot.get("ok") is not True:
        return None
    digest = snapshot.get("focus_sha256")
    return digest if isinstance(digest, str) and len(digest) == 64 else None


def tab_to_next_focus(controller, observer, direction="forward"):
    """Move focus one step with Tab/Shift+Tab and require a usable baseline."""
    direction = str(direction or "").strip().casefold()
    if direction not in {"forward", "backward"}:
        return {"ok": False, "error": "invalid_focus_navigation_direction"}
    try:
        before = observer.focused_control()
        before_digest = _focus_digest(before)
        if before_digest is None:
            return {"ok": False, "error": "focused_control_observation_unavailable"}
        if direction == "backward":
            controller.hotkey("shift", "tab")
        else:
            controller.press("tab")
        return {"ok": True, "action": "desktop_focus_navigate", "direction": direction,
                "_postcondition_context": {"before_focus_sha256": before_digest,
                    "direction": direction}}
    except Exception as exc:
        return {"ok": False, "error": f"focus_navigation_failed:{type(exc).__name__}"}


def verify_focus_navigation(observer, args, result):
    from ..execution.postconditions import PostconditionResult
    args = args if isinstance(args, dict) else {}
    context = result.get("_postcondition_context") if isinstance(result, dict) else None
    direction = str(args.get("direction", "forward")).strip().casefold()
    valid = (isinstance(result, dict) and result.get("ok") is True
             and result.get("action") == "desktop_focus_navigate"
             and direction in {"forward", "backward"}
             and result.get("direction") == direction
             and isinstance(context, dict) and context.get("direction") == direction
             and isinstance(context.get("before_focus_sha256"), str)
             and len(context["before_focus_sha256"]) == 64)
    if not valid:
        return PostconditionResult(False, {"observed": False}, "focus_navigation_binding_invalid")
    try:
        after = observer.focused_control()
        after_digest = _focus_digest(after)
        if after_digest is None:
            return PostconditionResult(False, {"observed": False}, "focused_control_readback_unavailable")
    except Exception as exc:
        return PostconditionResult(False, {"observed": False}, f"focused_control_readback_failed:{type(exc).__name__}")
    changed = after_digest != context["before_focus_sha256"]
    evidence = {"observed": True, "focus_changed": changed,
                "before_focus_sha256": context["before_focus_sha256"],
                "after_focus_sha256": after_digest, "direction": direction}
    return PostconditionResult(changed, evidence,
        "focus_transition_observed" if changed else "focus_transition_not_observed")
