"""Coordinate click wrapper that requires a fresh accessible state transition."""
from __future__ import annotations

import hashlib


def _digest(value: str) -> str:
    return hashlib.sha256(value.casefold().encode("utf-8")).hexdigest()


def click_with_expected_text(controller, observer, x, y, expected_text: str):
    """Click one in-bounds point only when expected text is absent before the click."""
    expected = str(expected_text or "").strip()
    try:
        x_value, y_value = int(x), int(y)
    except (TypeError, ValueError, OverflowError):
        return {"ok": False, "error": "invalid_desktop_click_coordinates"}
    if (not expected or len(expected) > 256 or isinstance(x, bool) or isinstance(y, bool)
            or str(x_value) != str(x).strip() or str(y_value) != str(y).strip()):
        return {"ok": False, "error": "invalid_verified_desktop_click_request"}
    try:
        size = controller.screen_size()
        width, height = int(size["width"]), int(size["height"])
        if width <= 0 or height <= 0 or not (0 <= x_value < width and 0 <= y_value < height):
            return {"ok": False, "error": "desktop_click_out_of_bounds"}
        before = observer.visible_texts()
        if not isinstance(before, list):
            return {"ok": False, "error": "desktop_observer_invalid_result"}
        if any(expected.casefold() in str(value).casefold() for value in before):
            return {"ok": False, "error": "expected_text_already_visible"}
        controller.click(x_value, y_value)
        return {"ok": True, "action": "desktop_click_verified", "x": x_value, "y": y_value,
                "_postcondition_context": {"expected_absent_before": True,
                    "expected_text_sha256": _digest(expected)}}
    except Exception as exc:
        return {"ok": False, "error": f"desktop_click_observation_failed:{type(exc).__name__}"}


def verify_verified_desktop_click(observer, args, result):
    """Verify the expected text appears in a fresh UIA read after a coordinate click."""
    from ..execution.postconditions import PostconditionResult
    args = args if isinstance(args, dict) else {}
    expected = str(args.get("expected_text") or "").strip()
    context = result.get("_postcondition_context") if isinstance(result, dict) else None
    try:
        x, y = int(args.get("x")), int(args.get("y"))
    except (TypeError, ValueError, OverflowError):
        x, y = -1, -1
    valid = (bool(expected) and len(expected) <= 256 and x >= 0 and y >= 0
             and isinstance(result, dict) and result.get("ok") is True
             and result.get("action") == "desktop_click_verified"
             and result.get("x") == x and result.get("y") == y
             and isinstance(context, dict) and context.get("expected_absent_before") is True
             and context.get("expected_text_sha256") == _digest(expected))
    if not valid:
        return PostconditionResult(False, {"observed": False}, "desktop_click_binding_invalid")
    try:
        names = observer.visible_texts()
        if not isinstance(names, list):
            raise TypeError("invalid UI Automation observation")
        found = any(expected.casefold() in str(value).casefold() for value in names)
    except Exception as exc:
        return PostconditionResult(False, {"observed": False}, f"desktop_click_readback_failed:{type(exc).__name__}")
    evidence = {"observed": True, "expected_text_visible": found,
                "expected_text_sha256": _digest(expected), "coordinates_bound": True}
    return PostconditionResult(found, evidence,
        "desktop_click_transition_observed" if found else "desktop_click_transition_not_observed")
