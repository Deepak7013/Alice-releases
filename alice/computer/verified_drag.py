"""Accessible-element drag with a fresh geometric UI Automation postcondition."""
from __future__ import annotations

import hashlib


_SOURCE_ROLES = frozenset({"list_item", "tree_item", "data_item"})
_TARGET_ROLES = frozenset({"list", "tree", "data_grid", "group", "pane", "list_item", "tree_item"})


def _name_digest(value):
    return hashlib.sha256(str(value or "").strip().casefold().encode("utf-8")).hexdigest()


def _bounds(row, screen):
    if not isinstance(row, dict) or not isinstance(row.get("bounds"), (list, tuple)):
        return None
    try:
        left, top, right, bottom = (int(value) for value in row["bounds"])
        width, height = int(screen["width"]), int(screen["height"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if (width <= 0 or height <= 0 or left < 0 or top < 0 or right <= left or bottom <= top
            or right > width or bottom > height):
        return None
    return (left, top, right, bottom)


def _center(bounds):
    left, top, right, bottom = bounds
    return ((left + right) // 2, (top + bottom) // 2)


def _inside(point, bounds):
    x, y = point
    left, top, right, bottom = bounds
    return left <= x < right and top <= y < bottom


def _unique(observer, name, role, screen):
    rows = observer.visible_element_bounds(name, role)
    if not isinstance(rows, list) or len(rows) != 1:
        return None
    row = rows[0]
    identity = row.get("identity_sha256")
    bounds = _bounds(row, screen)
    if (not bounds or row.get("enabled") is not True or not isinstance(identity, str)
            or len(identity) != 64):
        return None
    return {"identity_sha256": identity, "bounds": bounds}


def drag_accessible_element(controller, observer, source_name, target_name,
                            source_role="list_item", target_role="list"):
    """Drag one uniquely named accessible item into one accessible container.

    Only list/tree/grid item sources are allowed. Both elements must be unique,
    enabled, visible, and wholly on the primary screen. The source must begin
    outside the target; after the action an independent verifier checks that the
    source is still the same UIA element and its center is inside the target.
    """
    source_name = str(source_name or "").strip()
    target_name = str(target_name or "").strip()
    source_role = str(source_role or "").strip().casefold()
    target_role = str(target_role or "").strip().casefold()
    if (not source_name or not target_name or len(source_name) > 180 or len(target_name) > 180
            or source_role not in _SOURCE_ROLES or target_role not in _TARGET_ROLES):
        return {"ok": False, "error": "invalid_accessible_drag_request"}
    try:
        screen = controller.screen_size()
        source = _unique(observer, source_name, source_role, screen)
        target = _unique(observer, target_name, target_role, screen)
        if source is None or target is None:
            return {"ok": False, "error": "accessible_drag_target_not_unique_or_observable"}
        if source["identity_sha256"] == target["identity_sha256"]:
            return {"ok": False, "error": "accessible_drag_source_equals_target"}
        start = _center(source["bounds"])
        destination = _center(target["bounds"])
        if _inside(start, target["bounds"]):
            return {"ok": False, "error": "accessible_drag_source_already_inside_target"}
        controller.drag(*start, *destination, duration=0.5)
        return {
            "ok": True,
            "action": "desktop_drag_accessible_verified",
            "source_sha256": _name_digest(source_name),
            "source_role": source_role,
            "target_sha256": _name_digest(target_name),
            "target_role": target_role,
            "_postcondition_context": {
                "source_identity_sha256": source["identity_sha256"],
                "target_identity_sha256": target["identity_sha256"],
                "source_before_bounds": list(source["bounds"]),
                "target_before_bounds": list(target["bounds"]),
                "source_sha256": _name_digest(source_name),
                "source_role": source_role,
                "target_sha256": _name_digest(target_name),
                "target_role": target_role,
            },
        }
    except Exception as exc:
        return {"ok": False, "error": f"accessible_drag_failed:{type(exc).__name__}"}


def verify_accessible_drag_postcondition(observer, args, result):
    """Require a fresh UIA observation showing this item inside this target."""
    from ..execution.postconditions import PostconditionResult

    args = args if isinstance(args, dict) else {}
    context = result.get("_postcondition_context") if isinstance(result, dict) else None
    source_name = str(args.get("source_name") or "").strip()
    target_name = str(args.get("target_name") or "").strip()
    source_role = str(args.get("source_role", "list_item")).strip().casefold()
    target_role = str(args.get("target_role", "list")).strip().casefold()
    source_hash, target_hash = _name_digest(source_name), _name_digest(target_name)
    valid = (
        bool(source_name) and bool(target_name)
        and source_role in _SOURCE_ROLES and target_role in _TARGET_ROLES
        and isinstance(result, dict) and result.get("ok") is True
        and result.get("action") == "desktop_drag_accessible_verified"
        and result.get("source_sha256") == source_hash
        and result.get("target_sha256") == target_hash
        and result.get("source_role") == source_role
        and result.get("target_role") == target_role
        and isinstance(context, dict)
        and context.get("source_sha256") == source_hash
        and context.get("target_sha256") == target_hash
        and context.get("source_role") == source_role
        and context.get("target_role") == target_role
        and isinstance(context.get("source_identity_sha256"), str)
        and len(context["source_identity_sha256"]) == 64
        and isinstance(context.get("target_identity_sha256"), str)
        and len(context["target_identity_sha256"]) == 64
    )
    if not valid:
        return PostconditionResult(False, {"observed": False}, "accessible_drag_binding_invalid")
    large_screen = {"width": 2**31 - 1, "height": 2**31 - 1}
    before_source = _bounds({"bounds": context.get("source_before_bounds")}, large_screen)
    before_target = _bounds({"bounds": context.get("target_before_bounds")}, large_screen)
    if (before_source is None or before_target is None
            or _inside(_center(before_source), before_target)):
        return PostconditionResult(False, {"observed": False}, "accessible_drag_baseline_invalid")
    try:
        screen = large_screen
        source_rows = observer.visible_element_bounds(source_name, source_role)
        target_rows = observer.visible_element_bounds(target_name, target_role)
        if not isinstance(source_rows, list) or len(source_rows) != 1:
            raise ValueError("source not unique")
        if not isinstance(target_rows, list) or len(target_rows) != 1:
            raise ValueError("target not unique")
        source_row, target_row = source_rows[0], target_rows[0]
        source_bounds = _bounds(source_row, screen)
        target_bounds = _bounds(target_row, screen)
        if source_bounds is None or target_bounds is None:
            raise ValueError("element geometry unavailable")
    except Exception as exc:
        return PostconditionResult(False, {"observed": False}, f"accessible_drag_readback_failed:{type(exc).__name__}")

    source_identity_matches = source_row.get("identity_sha256") == context["source_identity_sha256"]
    target_identity_matches = target_row.get("identity_sha256") == context["target_identity_sha256"]
    source_moved = source_bounds != before_source
    inside = _inside(_center(source_bounds), target_bounds)
    observed = (source_identity_matches and target_identity_matches and source_moved and inside
                and source_row.get("enabled") is True)
    evidence = {
        "observed": True,
        "source_identity_matches": source_identity_matches,
        "target_identity_matches": target_identity_matches,
        "source_bounds_changed": source_moved,
        "source_center_inside_target": inside,
        "source_sha256": source_hash,
        "target_sha256": target_hash,
        "source_role": source_role,
        "target_role": target_role,
    }
    return PostconditionResult(observed, evidence,
        "accessible_drag_postcondition_observed" if observed else "accessible_drag_postcondition_not_observed")
