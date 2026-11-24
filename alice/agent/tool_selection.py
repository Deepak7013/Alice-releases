"""Choose a compact, relevant view of ALICE's registered tools for local planning.

This is prompt selection only. The registry and executor remain the authority for
what can run, and a low-confidence query receives the entire catalog.
"""

import re


_STOP = frozenset({
    "a", "an", "and", "are", "at", "can", "do", "for", "from", "i", "in",
    "is", "it", "me", "my", "of", "on", "please", "the", "then", "this",
    "to", "with", "you",
})
_ALIASES = {
    "launch": "open", "start": "open",
    "application": "app", "program": "app", "software": "app",
    "site": "website", "url": "website", "webpage": "website",
    "internet": "web", "online": "web", "lookup": "search", "find": "search",
    "research": "acquire",
    "computer": "desktop", "pc": "desktop", "laptop": "desktop",
    "mobile": "android", "phone": "android",
    "calculate": "math", "compute": "math", "multiply": "math",
    "mail": "email", "improve": "upgrade", "develop": "upgrade",
}
_FINANCE_TERMS = frozenset({
    "stock", "stocks", "market", "trading", "trade", "crypto", "bitcoin",
    "btc", "ethereum", "eth", "futures", "investment", "portfolio", "finance",
    "chart", "charts", "candle", "candles", "paper",
})
_UNVERIFIED_DESKTOP_TOOLS = frozenset({
    # Legacy raw input tools have no independent postcondition. Their verified
    # replacements remain registered for compatibility but are the only ones
    # exposed to the planner.
    "click", "double_click", "scroll", "type_text", "press_key", "hotkey", "drag",
})
_STATE_INDEPENDENT_TOOLS = frozenset({
    "acquire_knowledge", "search_knowledge", "trading_scope",
    "trading_knowledge", "market_research", "trading_backtest",
    "crypto_daily_history", "self_upgrade", "battery_status",
    "list_files", "read_file", "write_file",
})
_DESKTOP_CONTEXT = re.compile(
    r"\b(?:desktop|pc|computer|laptop|monitor|screen|foreground window|"
    r"mouse|keyboard|start button)\b", re.IGNORECASE,
)
_DESKTOP_VERBS = {
    "click": {"desktop_observe_actions", "desktop_click_accessible", "desktop_click_verified"},
    "tap": {"desktop_observe_actions", "desktop_click_accessible", "desktop_click_verified"},
    "type": {"desktop_focused_control", "desktop_type_verified"},
    "press": {"desktop_focused_control", "desktop_press_verified", "desktop_focus_navigate"},
    "scroll": {"desktop_observe_actions", "desktop_scroll_verified"},
    "drag": {"desktop_observe_actions", "desktop_drag_accessible"},
    "move": {"desktop_move_verified"},
}
_BROWSER_CONTEXT = re.compile(r"\b(?:browser|website|webpage|web page|tab|url)\b",re.IGNORECASE)
_BROWSER_VERBS = {
    "click": {"browser_click_role", "browser_click_text"},
    "tap": {"browser_click_role", "browser_click_text"},
    "open": {"browser_open", "browser_new_tab"},
    "go": {"browser_open", "browser_new_tab"},
    "navigate": {"browser_open", "browser_new_tab"},
    "fill": {"browser_fill"},
    "type": {"browser_fill"},
    "press": {"browser_press"},
    "switch": {"browser_tabs", "browser_switch_tab"},
}


def _explicit_browser_tools(request,catalog):
    text=str(request or "")
    if not _BROWSER_CONTEXT.search(text):
        return None
    lower=text.casefold()
    names={name for name in ("browser_snapshot", "browser_page_text") if name in catalog}
    for verb,tools in _BROWSER_VERBS.items():
        if re.search(rf"\b{verb}(?:es|s|ed|ing)?\b",lower):
            names.update(tools)
    names.intersection_update(catalog)
    return {name:catalog[name] for name in sorted(names)} if names else None


def _explicit_desktop_tools(request, catalog):
    text=str(request or "")
    if not _DESKTOP_CONTEXT.search(text):
        return None
    lower=text.casefold()
    if re.search(r"\b(?:browser|website|webpage|web page|website|url|tab)\b",lower):
        return None
    names=set()
    for verb, tools in _DESKTOP_VERBS.items():
        if re.search(rf"\b{verb}(?:s|ed|ing)?\b",lower):
            names.update(tools)
    names.intersection_update(catalog)
    if not names:
        return None
    # A screenshot/state read grounds coordinates and the current window when
    # the user asked for a visible desktop action.
    names.update({name for name in ("screen_state", "take_screenshot", "world_state")
                  if name in catalog})
    return {name:catalog[name] for name in sorted(names)} if names else None


def _tokens(value):
    words = re.findall(r"[a-z0-9]+", str(value).lower())
    tokens = {_ALIASES.get(word, word) for word in words if word not in _STOP}
    if re.search(r"\b(?:yourself|your own)\b", str(value).lower()):
        tokens.add("self")
    return tokens


def select_tools(request, registry, *, limit=16):
    """Return tool descriptions and names; fall back to all on weak evidence.

    Name matches carry more weight than descriptions so a broad description
    cannot crowd out the exact tool the user requested. A complete tie at the
    cutoff is treated as ambiguous and receives the full catalog.
    """
    text=str(request or "")
    explicit_browser=bool(_BROWSER_CONTEXT.search(text) or
                          re.search(r"\bhttps?://",text,re.IGNORECASE))
    explicit_desktop=bool(_DESKTOP_CONTEXT.search(text) and not explicit_browser)
    catalog = {name:info for name,info in registry.describe().items()
               if name not in _UNVERIFIED_DESKTOP_TOOLS
               and not (explicit_desktop and name.startswith("browser_"))}
    browser_tools=_explicit_browser_tools(request,catalog)
    if browser_tools is not None:
        return browser_tools
    desktop_tools=_explicit_desktop_tools(request,catalog)
    if desktop_tools is not None:
        return desktop_tools
    if ("read_file" in catalog and re.fullmatch(
            r"\s*(?:please\s+)?read\s+(?:the\s+file\s+)?[\"'`]?.+?[\"'`]?\s+"
            r"(?:from|in)\s+(?:my\s+)?(?:alice\s+)?workspace\s*[.!?]*\s*",
            text, re.IGNORECASE)):
        # Keep an explicit workspace read from being broadened to write tools
        # merely because both descriptions mention the workspace.
        return {"read_file": catalog["read_file"]}
    if len(catalog) <= limit:
        return catalog
    requested = _tokens(request)
    if not requested:
        return catalog
    ranked = []
    for name, info in catalog.items():
        if (name == "acquire_knowledge" and "saved" in requested and
                not (requested & {"acquire", "web"})):
            # Searching ALICE's saved memory should not trigger new web research.
            continue
        if name == "battery_status" and "acquire" in requested and not (
            requested & {"status", "level", "charge", "health", "percentage", "remaining"}
        ):
            # A technology research request is not a request for the PC sensor.
            continue
        if name.startswith(("market_", "trading_", "crypto_")) and not (requested & _FINANCE_TERMS):
            continue
        if "futures" in requested and name in {"trading_backtest", "crypto_daily_history", "paper_order"}:
            # The current simulator cannot represent contracts, margin or rolls.
            continue
        name_tokens = _tokens(name)
        description_tokens = _tokens(info.get("description", ""))
        name_hits = requested & name_tokens
        description_hits = requested & description_tokens
        score = 5 * len(name_hits) + len(description_hits)
        if name == "trading_scope" and requested & _FINANCE_TERMS:
            score += 5
        if name_tokens and name_tokens <= requested:
            score += 5
        if score >= 5:
            ranked.append((score, name))
    if not ranked or max(score for score, _ in ranked) < 5:
        return catalog
    ranked.sort(key=lambda item: (-item[0], item[1]))
    if len(ranked) > limit and ranked[limit - 1][0] == ranked[limit][0]:
        return catalog
    selected = {name for _, name in ranked[:limit]}
    if "open_app" in selected and "discover_apps" in catalog and len(selected) < limit:
        selected.add("discover_apps")
    # These registered tools inspect their own target data or project source;
    # adding a broad machine-state read only makes the model prompt and plan
    # noisier. Keep world_state available for app/device/system operations.
    state_independent=bool(selected) and selected.issubset(_STATE_INDEPENDENT_TOOLS)
    if "world_state" in catalog and len(selected) < limit and not state_independent:
        selected.add("world_state")
    return {name: catalog[name] for name in sorted(selected)}
