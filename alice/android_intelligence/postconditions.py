"""Independent postcondition observers for Android control tools."""
from __future__ import annotations

import hashlib
import re

from ..execution.postconditions import PostconditionResult


_PACKAGE_NAME = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$")


def _focused_editable_fields(state):
    return [
        element for element in getattr(state, "elements", [])
        if getattr(element, "focused", False)
        and "edittext" in str(getattr(element, "class_name", "")).casefold()
    ]


def _field_identity(element):
    resource_id = str(getattr(element, "resource_id", "") or "")
    class_name = str(getattr(element, "class_name", "") or "")
    bounds = tuple(getattr(element, "bounds", ()) or ())
    if not class_name or (not resource_id and (len(bounds) != 4 or not any(bounds))):
        raise ValueError("Focused Android edit field has no stable identity")
    # Layout bounds can legitimately change when an input action button
    # replaces the empty-state voice control. Prefer the stable accessibility
    # resource ID and widget class; use bounds only for anonymous fields.
    raw = "\0".join((resource_id, class_name)) if resource_id else "\0".join((class_name, ",".join(map(str, bounds))))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalized(value):
    return " ".join(str(value or "").split())


def _visible_values(state):
    values=[]
    for element in getattr(state,"elements",[]):
        values.extend((_normalized(getattr(element,"text","")),
                       _normalized(getattr(element,"content_desc",""))))
    return [value for value in values if value]


def _capture_android_transition(observer,serial,expected_text=None,expected_package=None):
    serial=str(serial or "").strip()
    expected_text=_normalized(expected_text)
    expected_package=str(expected_package or "").strip()
    has_text=bool(expected_text);has_package=bool(expected_package)
    if not serial or has_text==has_package:
        raise ValueError("Android action requires a serial and exactly one expected result")
    if has_text and len(expected_text)>256:
        raise ValueError("Expected Android UI text is limited to 256 characters")
    if has_package and not _PACKAGE_NAME.fullmatch(expected_package):
        raise ValueError("Expected Android package is invalid")
    before=observer.observe(serial)
    if str(getattr(before,"serial",""))!=serial:
        raise ValueError("Android observer returned state for a different device")
    before_package=str(getattr(before,"package","") or "").strip()
    if not before_package:
        raise ValueError("Android action requires an observed foreground package")
    if has_package and expected_package.casefold()==before_package.casefold():
        raise ValueError("Expected package must differ from the current foreground package")
    if has_text and expected_text in _visible_values(before):
        raise ValueError("Expected Android text must not already be visible before the action")
    return serial,expected_text,expected_package,before,before_package,has_text


def _android_action_context(serial,before_package,expected_text,has_text,action,target):
    return {"device_sha256":hashlib.sha256(serial.encode("utf-8")).hexdigest()[:16],
            "foreground_before":before_package,"expected_kind":"text" if has_text else "package",
            "expected_text_absent_before":has_text,"action":action,
            "target_sha256":hashlib.sha256(str(target).encode("utf-8")).hexdigest()}


def _android_action_target(args,action):
    if action=="tap":return _normalized(args.get("target_text"))
    if action=="keyevent":return str(args.get("key") or "").upper()
    if action=="swipe":
        coords=[args.get(k) for k in ("x1","y1","x2","y2")]
        if any(not isinstance(x,int) for x in coords):return ""
        duration=args.get("duration_ms",400)
        if not isinstance(duration,int):return ""
        return ",".join(map(str,[*coords,duration]))
    return ""


def tap_android_element_with_expected_transition(controller,observer,serial,target_text,
                                                 *,expected_text=None,expected_package=None):
    """Tap one uniquely observed clickable element; require a new observable UI state."""
    serial=str(serial or "").strip()
    target=_normalized(target_text)
    expected_text=_normalized(expected_text)
    expected_package=str(expected_package or "").strip()
    has_text=bool(expected_text)
    has_package=bool(expected_package)
    if not serial or not target or has_text==has_package:
        raise ValueError("Android tap requires a serial, target text, and exactly one expected result")
    if has_text and len(expected_text)>256:
        raise ValueError("Expected Android UI text is limited to 256 characters")
    if has_package and not _PACKAGE_NAME.fullmatch(expected_package):
        raise ValueError("Expected Android package is invalid")
    before=observer.observe(serial)
    if str(getattr(before,"serial",""))!=serial:
        raise ValueError("Android observer returned state for a different device")
    before_package=str(getattr(before,"package","") or "").strip()
    if not before_package:
        raise ValueError("Android tap requires an observed foreground package")
    if has_package and expected_package.casefold()==before_package.casefold():
        raise ValueError("Expected package must differ from the current foreground package")
    if has_text and expected_text in _visible_values(before):
        raise ValueError("Expected Android text must not already be visible before the tap")
    matches=[]
    for element in getattr(before,"elements",[]):
        candidates={_normalized(getattr(element,"text","")),
                    _normalized(getattr(element,"content_desc","")),
                    _normalized(getattr(element,"resource_id",""))}
        if target in candidates and getattr(element,"clickable",False) and getattr(element,"enabled",True):
            bounds=tuple(getattr(element,"bounds",()) or ())
            if len(bounds)==4 and bounds[2]>bounds[0] and bounds[3]>bounds[1]:
                matches.append(element)
    if len(matches)!=1:
        raise ValueError("Android tap target must be one unique, enabled, clickable visible element")
    action=controller.click(serial,matches[0])
    action_ok=bool(getattr(action,"ok",False) if not isinstance(action,dict) else action.get("ok"))
    context=_android_action_context(serial,before_package,expected_text,has_text,"tap",target)
    return {"ok":action_ok,"action":"tap","_postcondition_context":context}


def press_android_key_with_expected_transition(controller,observer,serial,key,
                                               *,expected_text=None,expected_package=None):
    serial,expected_text,expected_package,before,before_package,has_text=_capture_android_transition(
        observer,serial,expected_text,expected_package)
    key=str(key or "").strip().upper()
    allowed={"HOME","BACK","ENTER","TAB","ESCAPE","APP_SWITCH","POWER"}
    if key not in allowed:
        raise ValueError("Android key is outside the safe key allowlist")
    if key in {"ENTER","TAB"}:
        focused=[e for e in getattr(before,"elements",[]) if getattr(e,"focused",False) and getattr(e,"enabled",True)]
        if len(focused)!=1:
            raise ValueError("Android ENTER/TAB requires exactly one focused enabled control")
    action=controller.press(serial,key)
    ok=bool(getattr(action,"ok",False) if not isinstance(action,dict) else action.get("ok"))
    return {"ok":ok,"action":"keyevent","_postcondition_context":
            _android_action_context(serial,before_package,expected_text,has_text,"keyevent",key)}


def swipe_android_with_expected_transition(controller,observer,serial,x1,y1,x2,y2,duration_ms=400,
                                           *,expected_text=None,expected_package=None):
    serial,expected_text,expected_package,_before,before_package,has_text=_capture_android_transition(
        observer,serial,expected_text,expected_package)
    coords=(x1,y1,x2,y2)
    if any(not isinstance(x,int) or x<0 or x>20000 for x in coords):
        raise ValueError("Android swipe coordinates must be bounded non-negative integers")
    if not isinstance(duration_ms,int) or not 50<=duration_ms<=5000:
        raise ValueError("Android swipe duration must be between 50 and 5000 milliseconds")
    action=controller.swipe(serial,*coords,duration_ms)
    ok=bool(getattr(action,"ok",False) if not isinstance(action,dict) else action.get("ok"))
    target=",".join(map(str,[*coords,duration_ms]))
    return {"ok":ok,"action":"swipe","_postcondition_context":
            _android_action_context(serial,before_package,expected_text,has_text,"swipe",target)}


def verify_android_tap_postcondition(observer,args,result):
    """Independently verify the expected accessibility-tree transition after a tap."""
    args=args if isinstance(args,dict) else {}
    context=result.get("_postcondition_context") if isinstance(result,dict) else None
    serial=str(args.get("serial") or "").strip()
    expected_text=_normalized(args.get("expected_text"))
    expected_package=str(args.get("expected_package") or "").strip()
    has_text=bool(expected_text);has_package=bool(expected_package)
    action=str(context.get("action") or "tap") if isinstance(context,dict) else ""
    target=_android_action_target(args,action)
    device_hash=hashlib.sha256(serial.encode("utf-8")).hexdigest()[:16] if serial else ""
    if (not serial or not target or has_text==has_package or not isinstance(context,dict)
            or context.get("device_sha256")!=device_hash
            or context.get("expected_kind")!=("text" if has_text else "package")
            or context.get("action")!=action
            or context.get("target_sha256")!=hashlib.sha256(target.encode("utf-8")).hexdigest()
            or not isinstance(context.get("foreground_before"),str)
            or not isinstance(result,dict) or result.get("ok") is not True
            or result.get("action")!=action or not target):
        return PostconditionResult(False,{"observed":False},"android_tap_baseline_or_target_invalid")
    try:
        state=observer.observe(serial)
        same_device=str(getattr(state,"serial",""))==serial
        foreground=str(getattr(state,"package","") or "").strip()
        if has_text:
            visible=expected_text in _visible_values(state)
            same_package=foreground.casefold()==context["foreground_before"].casefold()
            matches=same_device and bool(foreground) and same_package and visible and context.get("expected_text_absent_before") is True
            evidence={"observed":same_device and bool(foreground),"expected_text_visible":visible,
                      "same_foreground_package":same_package,"expected_text_sha256":hashlib.sha256(expected_text.encode("utf-8")).hexdigest(),
                      "target_text_sha256":hashlib.sha256(target.encode("utf-8")).hexdigest(),"device_sha256":device_hash}
        else:
            package_matches=foreground.casefold()==expected_package.casefold()
            package_changed=foreground.casefold()!=context["foreground_before"].casefold()
            matches=same_device and bool(foreground) and package_matches and package_changed
            evidence={"observed":same_device and bool(foreground),"expected_package_matches":package_matches,
                      "foreground_package_changed":package_changed,"target_text_sha256":hashlib.sha256(target.encode("utf-8")).hexdigest(),
                      "device_sha256":device_hash}
    except Exception as exc:
        return PostconditionResult(False,{"observed":False,"device_sha256":device_hash},
                                   f"android_tap_readback_failed:{type(exc).__name__}")
    return PostconditionResult(matches,evidence,
        f"android_{action}_expected_transition_observed" if matches else f"android_{action}_postcondition_not_observed")


def capture_android_text_baseline(observer, serial):
    serial = str(serial or "").strip()
    if not serial:
        raise ValueError("An explicit Android serial is required for text readback")
    state = observer.observe(serial)
    fields = _focused_editable_fields(state)
    if len(fields) != 1:
        raise ValueError("Focus exactly one identifiable Android edit field before typing")
    field = fields[0]
    identity = _field_identity(field)
    field_text = str(getattr(field, "text", "") or "")
    field_hint = str(getattr(field, "hint", "") or "")
    # WhatsApp may expose its composer placeholder as EditText text and omit
    # the hint. In that case require its independent empty-composer control:
    # exactly one enabled voice-note control and no send control. The word
    # "Message" alone is never treated as proof of an empty field.
    state_package = str(getattr(state, "package", "") or "").casefold()
    field_id = str(getattr(field, "resource_id", "") or "").casefold()
    elements = list(getattr(state, "elements", []) or [])
    voice_controls = [e for e in elements if str(getattr(e, "resource_id", "") or "").casefold().endswith("/voice_note_btn")]
    send_controls = [e for e in elements if str(getattr(e, "resource_id", "") or "").casefold().rsplit("/", 1)[-1] in {"send", "send_btn", "send_button"}]
    whatsapp_empty_signal = (
        state_package == "com.whatsapp"
        and field_id.endswith("/entry")
        and field_text.strip() == "Message"
        and not field_hint.strip()
        and len(voice_controls) == 1
        and bool(getattr(voice_controls[0], "enabled", False))
        and not send_controls
    )
    placeholder_only = bool(field_hint and field_text == field_hint) or whatsapp_empty_signal
    return {
        "device_sha256": hashlib.sha256(serial.encode("utf-8")).hexdigest()[:16],
        "package": str(getattr(state, "package", "") or ""),
        "activity": str(getattr(state, "activity", "") or ""),
        "field_identity": identity,
        "field_hint": field_hint,
        "before_text": "" if placeholder_only else field_text,
        "placeholder_only": placeholder_only,
        "placeholder_signal": "explicit_hint" if field_hint and field_text == field_hint else (
            "whatsapp_voice_note_control" if whatsapp_empty_signal else "none"
        ),
        "screen_fingerprint": str(getattr(state, "fingerprint", "") or ""),
    }


def type_android_text_with_baseline(controller, observer, serial, text, *, baseline=None):
    serial = str(serial or "").strip()
    text = str(text or "")
    if not text:
        raise ValueError("Android text entry requires non-empty text")
    baseline = baseline if baseline is not None else capture_android_text_baseline(observer, serial)
    expected_device = hashlib.sha256(serial.encode("utf-8")).hexdigest()[:16]
    if not isinstance(baseline, dict) or baseline.get("device_sha256") != expected_device:
        raise ValueError("Android text baseline does not belong to the requested device")
    result = controller.text(text, serial)
    public = dict(result) if isinstance(result, dict) else {"ok": bool(result)}
    public["_postcondition_context"] = {"android_text_baseline": baseline}
    return public


def verify_android_launch_postcondition(observer, args, _result):
    """Confirm that the requested Android package is the observed foreground app."""
    serial = str((args or {}).get("serial") or "").strip()
    package = str((args or {}).get("package") or "").strip()
    if not serial or not _PACKAGE_NAME.fullmatch(package):
        return PostconditionResult(
            False,
            {"observed": False},
            "android_launch_target_or_device_missing",
        )
    try:
        state = observer.observe(serial)
    except Exception as exc:
        return PostconditionResult(
            False,
            {"observed": False, "device_sha256": hashlib.sha256(serial.encode("utf-8")).hexdigest()[:16]},
            f"android_foreground_observation_failed:{type(exc).__name__}",
        )

    foreground = str(getattr(state, "package", "") or "").strip()
    activity = str(getattr(state, "activity", "") or "")
    matches = foreground.casefold() == package.casefold()
    evidence = {
        "observed": True,
        "device_sha256": hashlib.sha256(serial.encode("utf-8")).hexdigest()[:16],
        "requested_package": package,
        "foreground_package": foreground[:200],
        "foreground_activity": activity[:200],
        "package_matches": matches,
    }
    return PostconditionResult(
        matches,
        evidence,
        "requested_android_package_is_foreground" if matches else "requested_android_package_not_foreground",
    )


def verify_android_text_postcondition(observer, args, result):
    """Verify exact appended text in the same uniquely focused editable UI node."""
    args = args if isinstance(args, dict) else {}
    context = result.get("_postcondition_context") if isinstance(result, dict) else None
    baseline = context.get("android_text_baseline") if isinstance(context, dict) else None
    serial = str(args.get("serial") or "").strip()
    requested = str(args.get("text") or "")
    device_hash = hashlib.sha256(serial.encode("utf-8")).hexdigest()[:16] if serial else ""
    if not isinstance(baseline, dict) or not serial or not requested:
        return PostconditionResult(False, {"observed": False}, "android_text_baseline_missing")
    if baseline.get("device_sha256") != device_hash:
        return PostconditionResult(False, {"observed": False}, "android_text_baseline_device_mismatch")
    try:
        state = observer.observe(serial)
        fields = _focused_editable_fields(state)
        same_device = str(getattr(state, "serial", "")) == serial
        same_screen = (
            same_device
            and
            str(getattr(state, "package", "") or "") == str(baseline.get("package", ""))
            and str(getattr(state, "activity", "") or "") == str(baseline.get("activity", ""))
        )
        same_field = len(fields) == 1 and _field_identity(fields[0]) == baseline.get("field_identity")
    except Exception as exc:
        return PostconditionResult(
            False,
            {"observed": False, "device_sha256": device_hash},
            f"android_text_readback_failed:{type(exc).__name__}",
        )
    before = str(baseline.get("before_text", ""))
    after = str(getattr(fields[0], "text", "") or "") if same_field else ""
    before_fingerprint = str(baseline.get("screen_fingerprint", "") or "")
    after_fingerprint = str(getattr(state, "fingerprint", "") or "")
    fresh_observation = not (before_fingerprint and after_fingerprint and before_fingerprint == after_fingerprint)
    exact_append = same_field and after == before + requested and after != before
    evidence = {
        "observed": True,
        "device_sha256": device_hash,
        "same_screen": same_screen,
        "same_device": same_device,
        "fresh_observation": fresh_observation,
        "focused_editable_unique": len(fields) == 1,
        "same_field": same_field,
        "exact_append": exact_append,
        "requested_sha256": hashlib.sha256(requested.encode("utf-8")).hexdigest(),
        "before_value_sha256": hashlib.sha256(before.encode("utf-8")).hexdigest(),
        "after_value_sha256": hashlib.sha256(after.encode("utf-8")).hexdigest() if same_field else "",
    }
    ok = same_screen and same_device and fresh_observation and exact_append
    return PostconditionResult(
        ok,
        evidence,
        "android_text_exactly_observed_in_same_focused_field" if ok else "android_text_readback_not_exact",
    )
