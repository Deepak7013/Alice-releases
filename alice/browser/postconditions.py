"""Independent readback verifiers for controlled browser mutations."""
from __future__ import annotations

import hashlib
from urllib.parse import urlsplit, urlunsplit

from ..execution.postconditions import PostconditionResult


def _url_key(value):
    text=str(value or "").strip()
    try:
        parsed=urlsplit(text)
        scheme=parsed.scheme.casefold()
        if scheme in {"http","https"} and parsed.netloc:
            host=parsed.netloc.casefold()
            path=parsed.path or "/"
            return urlunsplit((scheme,host,path,parsed.query,parsed.fragment))
        if scheme=="about" and text.casefold()=="about:blank":
            return "about:blank"
    except Exception:
        return None
    return None


def verify_browser_open_postcondition(browser,args,result):
    requested=_url_key(args.get("url"))
    reported=_url_key(result.get("url")) if isinstance(result,dict) else None
    if not isinstance(result,dict) or result.get("ok") is not True or not requested or not reported:
        return PostconditionResult(False,{"observed":False},"browser_open_target_or_result_invalid")
    try:
        observed=browser.snapshot()
        actual=_url_key(observed.get("url")) if isinstance(observed,dict) else None
    except Exception:
        actual=None
    matches=bool(actual and actual==requested and actual==reported)
    return PostconditionResult(matches,{"observed":actual is not None,
        "requested_url_matches":bool(actual and actual==requested),
        "reported_url_matches_observation":bool(actual and actual==reported)},
        "active browser URL matches requested navigation" if matches else "browser_open_postcondition_not_observed")


def verify_browser_new_tab_postcondition(browser,args,result):
    context=result.get("_postcondition_context") if isinstance(result,dict) else None
    before=context.get("before_tab_count") if isinstance(context,dict) else None
    expected_index=context.get("new_tab_index") if isinstance(context,dict) else None
    requested=_url_key(args.get("url","about:blank"))
    reported=_url_key(result.get("url")) if isinstance(result,dict) else None
    if (not isinstance(result,dict) or result.get("ok") is not True
            or not isinstance(before,int) or not isinstance(expected_index,int)
            or not requested or not reported):
        return PostconditionResult(False,{"observed":False},"new_tab_baseline_or_result_invalid")
    try:
        observed=browser.snapshot()
        tabs=observed.get("tabs",[]) if isinstance(observed,dict) else []
        actual=_url_key(observed.get("url")) if isinstance(observed,dict) else None
        index_matches=(0<=expected_index<len(tabs) and _url_key(tabs[expected_index].get("url"))==requested)
        count_matches=len(tabs)==before+1
    except Exception:
        actual=None; index_matches=False; count_matches=False
    active_matches=bool(actual and actual==requested and actual==reported)
    ok=bool(count_matches and index_matches and active_matches)
    return PostconditionResult(ok,{"observed":actual is not None,"tab_count_incremented":bool(count_matches),
        "created_tab_matches":bool(index_matches),"active_tab_matches":active_matches},
        "new active tab observed" if ok else "browser_new_tab_postcondition_not_observed")


def verify_browser_switch_tab_postcondition(browser,args,result):
    index=args.get("index",0)
    reported=_url_key(result.get("url")) if isinstance(result,dict) else None
    if not isinstance(result,dict) or result.get("ok") is not True or not isinstance(index,int) or not reported:
        return PostconditionResult(False,{"observed":False},"browser_switch_result_invalid")
    try:
        observed=browser.snapshot()
        tabs=observed.get("tabs",[]) if isinstance(observed,dict) else []
        actual=_url_key(observed.get("url")) if isinstance(observed,dict) else None
        indexed=_url_key(tabs[index].get("url")) if 0<=index<len(tabs) else None
    except Exception:
        actual=None; indexed=None
    matches=bool(actual and actual==reported and actual==indexed)
    return PostconditionResult(matches,{"observed":actual is not None,
        "active_url_matches_result":bool(actual and actual==reported),"selected_index_matches":bool(actual and actual==indexed)},
        "selected browser tab observed" if matches else "browser_switch_tab_postcondition_not_observed")


def verify_browser_fill_postcondition(browser,args,result):
    label=str(args.get("label", ""))
    expected=str(args.get("text", ""))
    if not isinstance(result,dict) or result.get("ok") is not True or not label:
        return PostconditionResult(False,{"observed":False},"browser_fill_result_or_label_invalid")
    try:
        actual=str(browser.read_labeled_input(label))
    except Exception:
        return PostconditionResult(False,{"observed":False},"browser_fill_readback_unavailable")
    expected_hash=hashlib.sha256(expected.encode("utf-8")).hexdigest()
    actual_hash=hashlib.sha256(actual.encode("utf-8")).hexdigest()
    matches=actual_hash==expected_hash
    return PostconditionResult(matches,{"observed":True,"field_value_matches":matches,
        "label_sha256":hashlib.sha256(label.encode("utf-8")).hexdigest(),
        "value_sha256":actual_hash},
        "labeled input value independently reread" if matches else "browser_fill_postcondition_not_observed")


def verify_browser_click_postcondition(browser,args,result):
    """Verify a click only when its declared, previously absent state change is reread."""
    context=result.get("_postcondition_context") if isinstance(result,dict) else None
    expected_url=args.get("expected_url")
    expected_text=args.get("expected_text")
    has_url=isinstance(expected_url,str) and bool(expected_url.strip())
    has_text=isinstance(expected_text,str) and bool(expected_text.strip())
    if (not isinstance(result,dict) or result.get("ok") is not True
            or has_url == has_text or not isinstance(context,dict)
            or context.get("kind") != ("url" if has_url else "text")
            or not isinstance(context.get("before_url"),str)):
        return PostconditionResult(False,{"observed":False},"browser_click_expectation_or_result_invalid")
    try:
        observed=browser.snapshot()
        active=_url_key(observed.get("url")) if isinstance(observed,dict) else None
        reported=_url_key(result.get("url"))
        before=_url_key(context.get("before_url"))
        if has_url:
            requested=_url_key(expected_url)
            changed=bool(active and before and active!=before)
            matches=bool(requested and active==requested and reported==active and changed)
            evidence={"observed":active is not None,"expected_url_matches":bool(requested and active==requested),
                      "result_matches_readback":bool(active and reported==active),"url_changed":changed}
        else:
            expected=expected_text
            if len(expected)>256:
                return PostconditionResult(False,{"observed":False},"browser_click_expected_text_too_long")
            if context.get("expected_text_absent_before") is not True:
                return PostconditionResult(False,{"observed":False},"browser_click_baseline_invalid")
            visible=browser.page_text(max_chars=12000)
            body=str(visible.get("text","")) if isinstance(visible,dict) else ""
            visible_url=_url_key(visible.get("url")) if isinstance(visible,dict) else None
            matches=bool(expected and expected in body
                         and visible_url and active==visible_url and reported==active)
            evidence={"observed":visible_url is not None,"expected_text_visible":bool(expected and expected in body),
                      "result_matches_readback":bool(active and reported==active),
                      "expected_text_sha256":hashlib.sha256(expected.encode("utf-8")).hexdigest()}
    except Exception:
        return PostconditionResult(False,{"observed":False},"browser_click_readback_unavailable")
    return PostconditionResult(matches,evidence,
        "declared browser state change independently observed" if matches else "browser_click_postcondition_not_observed")


def verify_browser_recover_postcondition(browser, args, result):
    """Verify that recovery produced a live, independently readable browser state."""
    if not isinstance(result, dict) or result.get("ok") is not True or result.get("recovered") is not True:
        return PostconditionResult(False, {"observed": False}, "browser_recovery_result_invalid")
    reported_url = _url_key(result.get("url"))
    reported_title = result.get("title")
    reported_tabs = result.get("tabs")
    try:
        observed = browser.snapshot()
        actual_url = _url_key(observed.get("url")) if isinstance(observed, dict) else None
        actual_title = observed.get("title") if isinstance(observed, dict) else None
        actual_tabs = observed.get("tabs") if isinstance(observed, dict) else None
        usable_tabs = isinstance(actual_tabs, list) and len(actual_tabs) > 0
        url_matches = bool(actual_url and actual_url == reported_url)
        title_matches = isinstance(actual_title, str) and actual_title == reported_title
        tabs_match = (isinstance(reported_tabs, list) and usable_tabs
                      and len(actual_tabs) == len(reported_tabs))
    except Exception:
        return PostconditionResult(False, {"observed": False}, "browser_recovery_readback_unavailable")
    ok = bool(url_matches and title_matches and tabs_match)
    return PostconditionResult(ok, {"observed": actual_url is not None,
        "active_url_matches": url_matches, "title_matches": title_matches,
        "tabs_observed": bool(usable_tabs), "tab_count_matches": bool(tabs_match)},
        "recovered browser state independently observed" if ok else "browser_recovery_postcondition_not_observed")
