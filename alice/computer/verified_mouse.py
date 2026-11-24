"""Bounded pointer movement with fresh operating-system cursor readback."""
from __future__ import annotations


def _coordinate(value):
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if str(number) != str(value).strip():
        return None
    return number


def move_pointer_to_verified(controller, x, y):
    """Move the pointer only to an on-screen integer coordinate."""
    x_value, y_value = _coordinate(x), _coordinate(y)
    if x_value is None or y_value is None:
        return {"ok": False, "error": "invalid_verified_pointer_coordinates"}
    try:
        size = controller.screen_size()
        width, height = int(size["width"]), int(size["height"])
        if width <= 0 or height <= 0 or not (0 <= x_value < width and 0 <= y_value < height):
            return {"ok": False, "error": "verified_pointer_coordinate_out_of_bounds"}
        controller.move(x_value, y_value, duration=0.2)
        return {"ok": True, "action": "desktop_move_verified", "x": x_value, "y": y_value,
                "_postcondition_context": {"x": x_value, "y": y_value}}
    except Exception as exc:
        return {"ok": False, "error": f"verified_pointer_move_failed:{type(exc).__name__}"}


def verify_pointer_position_postcondition(observer, args, result):
    """Verify a fresh cursor query, independently of the move call result."""
    from ..execution.postconditions import PostconditionResult

    args = args if isinstance(args, dict) else {}
    x, y = _coordinate(args.get("x")), _coordinate(args.get("y"))
    context = result.get("_postcondition_context") if isinstance(result, dict) else None
    valid = (x is not None and y is not None
             and isinstance(result, dict) and result.get("ok") is True
             and result.get("action") == "desktop_move_verified"
             and result.get("x") == x and result.get("y") == y
             and isinstance(context, dict) and context.get("x") == x and context.get("y") == y)
    if not valid:
        return PostconditionResult(False, {"observed": False}, "pointer_move_binding_invalid")
    try:
        point = observer.mouse_position()
        actual = (_coordinate(point.get("x")), _coordinate(point.get("y"))) if isinstance(point, dict) else (None, None)
    except Exception as exc:
        return PostconditionResult(False, {"observed": False}, f"pointer_position_readback_failed:{type(exc).__name__}")
    matches = actual == (x, y)
    evidence = {"observed": True, "position_matches": matches,
                "requested_x": x, "requested_y": y}
    return PostconditionResult(matches, evidence,
        "pointer_position_observed" if matches else "pointer_position_not_observed")
