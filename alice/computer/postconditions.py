"""Independent Windows process-state observers for desktop launch tools."""
from __future__ import annotations

import hashlib
import ntpath
from pathlib import Path

from ..execution.postconditions import PostconditionResult


def _expected_process(command):
    value=str(command or "").strip()
    if not value or "\n" in value or "\r" in value:
        return ""
    if ntpath.isabs(value) and ntpath.splitext(value)[1].casefold()=='.exe':
        executable=value
    elif value.startswith('"'):
        end=value.find('"',1)
        if end<=1:return ""
        executable=value[1:end]
    else:
        executable=value.split(None,1)[0]
    # Commands may contain Windows paths even when this verifier is unit-tested
    # from a non-Windows host; ntpath handles both slash styles deterministically.
    name=ntpath.basename(executable.replace("/", "\\"))
    if not name or name in {".",".."}:
        return ""
    if Path(name).suffix.casefold() not in {"", ".exe"}:
        return ""
    return name if name.casefold().endswith(".exe") else name+".exe"


def verify_open_app_postcondition(discovery,args,result):
    """Verify the process created by this launch is still present under its requested image."""
    args=args if isinstance(args,dict) else {}
    command=str(args.get("command") or "").strip()
    expected=_expected_process(command)
    try:
        pid=int(result.get("pid")) if isinstance(result,dict) else 0
    except (TypeError,ValueError):
        pid=0
    if (not expected or pid<=0 or not isinstance(result,dict) or result.get("ok") is not True
            or result.get("action")!="open_app" or result.get("target")!=command):
        return PostconditionResult(False,{"observed":False},"desktop_launch_result_or_target_invalid")
    try:
        observed=discovery.process_by_pid(pid)
        rows=observed.get("processes",[]) if isinstance(observed,dict) else []
        matches=[row for row in rows if isinstance(row,dict) and row.get("pid")==pid
                 and str(row.get("image") or "").casefold()==expected.casefold()]
        is_running=bool(observed.get("ok") is True and len(matches)==1)
    except Exception as exc:
        return PostconditionResult(False,{"observed":False},f"desktop_process_readback_failed:{type(exc).__name__}")
    evidence={"observed":isinstance(observed,dict) and observed.get("ok") is True,
              "requested_process_running":is_running,
              "pid_bound":bool(matches) if isinstance(observed,dict) else False,
              "requested_process_sha256":hashlib.sha256(expected.casefold().encode("utf-8")).hexdigest()}
    return PostconditionResult(is_running,evidence,
        "requested_desktop_process_observed" if is_running else "requested_desktop_process_not_observed")


def verify_accessible_click_postcondition(observer,args,result):
    """Require a fresh foreground UIA read to find the requested new visible text."""
    args=args if isinstance(args,dict) else {}
    context=result.get("_postcondition_context") if isinstance(result,dict) else None
    expected=str(args.get("expected_text") or "").strip()
    target=str(args.get("name") or "").strip()
    expected_hash=hashlib.sha256(expected.casefold().encode("utf-8")).hexdigest() if expected else ""
    target_hash=hashlib.sha256(target.casefold().encode("utf-8")).hexdigest() if target else ""
    if (not expected or not target or len(expected)>256 or len(target)>180
            or not isinstance(result,dict) or result.get("ok") is not True
            or result.get("action")!="desktop_click_accessible"
            or result.get("target_sha256")!=target_hash
            or not isinstance(context,dict) or context.get("expected_absent_before") is not True
            or context.get("expected_text_sha256")!=expected_hash):
        return PostconditionResult(False,{"observed":False},"desktop_accessible_click_binding_invalid")
    try:
        names=observer.visible_texts()
        if not isinstance(names,list):
            raise TypeError("invalid UI Automation observation")
        found=any(expected.casefold() in str(value).casefold() for value in names)
    except Exception as exc:
        return PostconditionResult(False,{"observed":False},f"desktop_uia_readback_failed:{type(exc).__name__}")
    evidence={"observed":True,"expected_text_visible":found,
              "expected_text_sha256":expected_hash,"target_sha256":target_hash,
              "visible_element_count":min(len(names),300)}
    return PostconditionResult(found,evidence,
        "new_accessible_desktop_text_observed" if found else "expected_accessible_desktop_text_not_observed")
