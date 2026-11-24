"""Privacy-preserving desktop typing with independent editable-value readback."""
from __future__ import annotations

import hashlib
import string


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _valid_text(value) -> bool:
    # pyautogui.write is keyboard-layout dependent and not a Unicode text API.
    # This bounded path intentionally accepts only printable ASCII to avoid
    # silently mangling text or invoking control-key sequences.
    return (isinstance(value, str) and 0 < len(value) <= 500
            and all(char in string.printable and char not in "\r\n\t\x0b\x0c" for char in value))


def type_into_empty_focused_control(controller, observer, text):
    """Type only into one focused, non-password editable control proven empty."""
    if not _valid_text(text):
        return {"ok": False, "error": "desktop_text_must_be_printable_ascii_under_501_chars"}
    try:
        before = observer.focused_edit_value_fingerprint()
        if not isinstance(before, dict) or before.get("ok") is not True:
            return {"ok": False, "error": "focused_edit_observation_unavailable"}
        if before.get("value_length") != 0 or before.get("value_sha256") != _sha256(""):
            return {"ok": False, "error": "focused_edit_control_not_empty"}
        focus_hash = before.get("focus_sha256")
        if not isinstance(focus_hash, str) or len(focus_hash) != 64:
            return {"ok": False, "error": "focused_edit_identity_unavailable"}
        controller.type_text(text)
        return {"ok": True, "action": "desktop_type_verified", "text_length": len(text),
                "text_sha256": _sha256(text),
                "_postcondition_context": {"focus_sha256": focus_hash,
                    "baseline_value_sha256": _sha256(""), "expected_value_sha256": _sha256(text),
                    "expected_value_length": len(text)}}
    except Exception as exc:
        return {"ok": False, "error": f"desktop_typing_failed:{type(exc).__name__}"}


def verify_desktop_typing(observer, args, result):
    """Verify exact typed value by hash/length only; never return the field contents."""
    from ..execution.postconditions import PostconditionResult
    args = args if isinstance(args, dict) else {}
    text = args.get("text")
    context = result.get("_postcondition_context") if isinstance(result, dict) else None
    valid = (_valid_text(text) and isinstance(result, dict) and result.get("ok") is True
             and result.get("action") == "desktop_type_verified"
             and result.get("text_length") == len(text)
             and result.get("text_sha256") == _sha256(text)
             and isinstance(context, dict)
             and isinstance(context.get("focus_sha256"), str) and len(context["focus_sha256"]) == 64
             and context.get("baseline_value_sha256") == _sha256("")
             and context.get("expected_value_sha256") == _sha256(text)
             and context.get("expected_value_length") == len(text))
    if not valid:
        return PostconditionResult(False, {"observed": False}, "desktop_typing_binding_invalid")
    try:
        after = observer.focused_edit_value_fingerprint()
        if not isinstance(after, dict) or after.get("ok") is not True:
            raise TypeError("focused edit readback unavailable")
    except Exception as exc:
        return PostconditionResult(False, {"observed": False},
                                   f"desktop_typing_readback_failed:{type(exc).__name__}")
    same_focus = after.get("focus_sha256") == context["focus_sha256"]
    exact_value = (after.get("value_sha256") == context["expected_value_sha256"]
                   and after.get("value_length") == context["expected_value_length"])
    evidence = {"observed": True, "same_focused_control": same_focus,
                "expected_value_matches": exact_value,
                "expected_value_sha256": context["expected_value_sha256"],
                "observed_value_sha256": after.get("value_sha256"),
                "expected_value_length": context["expected_value_length"],
                "observed_value_length": after.get("value_length")}
    ok = same_focus and exact_value
    return PostconditionResult(ok, evidence,
        "desktop_typed_value_verified" if ok else "desktop_typed_value_mismatch")
