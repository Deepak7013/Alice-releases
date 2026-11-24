"""Deterministic intent routes for common assistant requests.

The router recognizes explicit app launches, public website navigation, and
web-research questions. Other requests continue through ALICE's existing
cognitive, policy, and planning paths.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
import ipaddress
from pathlib import Path
from urllib.parse import urlparse, urlunparse


_WAKE_PREFIX = re.compile(r"^(?:(?:hey|hi)\s+)?alice\b[,:\s-]*", re.IGNORECASE)
_OPEN_PATTERNS = (
    re.compile(
        r"^(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?(?:please\s+)?"
        r"(?:open|launch|start|bring\s+up|pull\s+up)\s+(.+?)\s*[.!?]*$",
        re.IGNORECASE,
    ),
    re.compile(r"^(?:please\s+)?(?:i\s+need|i\s+want)\s+(.+?)\s+open\s*[.!?]*$", re.IGNORECASE),
)
_OPEN_URL = re.compile(
    r"^(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?(?:please\s+)?"
    r"(?:open|go\s+to|navigate\s+to|visit)\s+"
    r"(?:(?:the\s+)?(?:website|site)\s+)?(.+?)\s*[.!?]*$",
    re.IGNORECASE,
)
_WEB_SEARCH = re.compile(
    r"^(?:please\s+)?(?:search\s+(?:(?:the\s+)?(?:web|internet|online)\s+)?"
    r"(?:for\s+)?|look\s+up\s+|research\s+(?:(?:the\s+)?(?:web|internet|online)\s+)?"
    r"(?:for\s+)?|find\s+online\s+|browse\s+for\s+)(.+?)\s*[.!?]*$",
    re.IGNORECASE,
)
_FRESHNESS = re.compile(
    r"\b(latest|today|tonight|right now|currently|current|recent news|this week|"
    r"this month|as of now|up to date)\b",
    re.IGNORECASE,
)
_INFORMATION_REQUEST = re.compile(
    r"^(?:what(?:\s+(?:is|are|was|were|does|do|did|happened|causes|caused)|'s\s+|'re\s+)|"
    r"who(?:\s+(?:is|are|was|were|won|invented)|'s\s+|'re\s+)|"
    r"where(?:\s+(?:is|are|was|were|can|do)|'s\s+|'re\s+)|"
    r"when(?:\s+(?:is|are|was|were|did|does|will)|'s\s+)|"
    r"why(?:\s+(?:is|are|was|were|does|do|did)|'s\s+)|"
    r"how(?:\s+(?:do|does|did|is|are|can|much|many|to)|'s\s+)|"
    r"which\s+|compare\s+|explain\s+|tell\s+me\s+(?:about\s+|what\s+|who\s+|where\s+|when\s+))",
    re.IGNORECASE,
)
_LOCAL_CONVERSATION = re.compile(
    r"^(?:"
    r"what\s+(?:do\s+you\s+think|is\s+your\s+(?:name|purpose|job)|can\s+you\s+do)|"
    r"what(?:'s|\s+is)\s+your\s+(?:name|purpose|job)|"
    r"who\s+are\s+you|tell\s+me\s+about\s+yourself|"
    r"how\s+are\s+you|are\s+you\s+(?:there|alive|okay|ok)|"
    r"do\s+you\s+(?:know\s+me|remember\s+me|have\s+a\s+name)"
    r")\b",
    re.IGNORECASE,
)
_SIMPLE_ARITHMETIC = re.compile(
    r"^(?:what\s+is\s+)?[-+]?\d+(?:\.\d+)?\s*[+*/x×-]\s*[-+]?\d+(?:\.\d+)?\??$",
    re.IGNORECASE,
)


def _name_key(value: str) -> str:
    return "".join(re.findall(r"[a-z0-9]+", str(value).casefold()))


class IntentRouter:
    """Resolve safe, high-confidence fast paths without an LLM round trip."""

    def __init__(self, app_discovery, web_research):
        self.app_discovery = app_discovery
        self.web_research = web_research

    @staticmethod
    def requested_app(text: str) -> str | None:
        request = " ".join(str(text or "").split())
        request = _WAKE_PREFIX.sub("", request, count=1)
        match = None
        for pattern in _OPEN_PATTERNS:
            match = pattern.match(request)
            if match:
                break
        if not match:
            return None
        name = match.group(1).strip().strip(" `\"'")
        name = re.sub(r"\s+(?:for me|please|now|right away)$", "", name, flags=re.IGNORECASE).strip()
        name = re.sub(r"\s+on\s+(?:my|the)\s+(?:pc|computer|laptop|desktop)$",
                      "", name, flags=re.IGNORECASE).strip()
        name = re.sub(r"^(?:the|a|an)\s+", "", name, flags=re.IGNORECASE).strip()
        name = re.sub(r"\s+(?:app|application|browser)$", "", name, flags=re.IGNORECASE).strip()
        if not name or len(name) > 100 or any(ch in name for ch in "\\/:;|<>\n\r"):
            return None
        return name

    @staticmethod
    def requested_url(text: str) -> str | None:
        """Parse an explicitly requested public website URL for safe navigation."""
        request = _WAKE_PREFIX.sub("", " ".join(str(text or "").split()), count=1)
        match = _OPEN_URL.match(request)
        if not match:
            return None
        candidate = match.group(1).strip().strip(" `\"'")
        if not candidate or len(candidate) > 2048 or any(ch.isspace() for ch in candidate):
            return None
        if not re.match(r"^[a-z][a-z0-9+.-]*://", candidate, re.IGNORECASE):
            candidate = "https://" + candidate
        try:
            parsed = urlparse(candidate)
            host = (parsed.hostname or "").casefold().rstrip(".")
            if (parsed.scheme.casefold() not in {"http", "https"} or not host
                    or parsed.username is not None or parsed.password is not None):
                return None
            # Accessing .port also validates malformed/out-of-range ports.
            _ = parsed.port
            if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
                return None
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                address = None
            if address is not None and not address.is_global:
                return None
            if "." not in host and address is None:
                return None
            return urlunparse(parsed._replace(fragment=""))
        except (ValueError, UnicodeError):
            return None

    def resolve_app(self, requested: str) -> dict:
        """Resolve a unique installed executable; otherwise return safe suggestions."""
        # Search the full Start Menu inventory so common spoken short names such
        # as “Chrome” can resolve to “Google Chrome” without guessing between apps.
        found = self.app_discovery.search("", limit=2000)
        apps = found.get("apps", []) if isinstance(found, dict) else []
        key = _name_key(requested)
        matches = []
        seen = set()
        for app in apps:
            if not isinstance(app, dict):
                continue
            app_key = _name_key(app.get("name", ""))
            # Exact names are preferred. A unique suffix match supports common
            # vendor-prefixed names (e.g. Chrome -> Google Chrome) while still
            # reporting ambiguity when more than one executable fits.
            if app_key != key and not (len(key) >= 3 and app_key.endswith(key)):
                continue
            kind=app.get("kind")
            if kind=="shortcut":
                shortcut=Path(str(app.get("path","")))
                resolver=getattr(self.app_discovery,"resolve_shortcut",None)
                target=resolver(shortcut) if callable(resolver) else None
                path=Path(target) if target else Path()
            else:
                path=Path(str(app.get("path", "")))
            if kind not in {"exe","shortcut"} or path.suffix.casefold()!=".exe":
                continue
            try:
                resolved = path.resolve(strict=True)
            except (OSError, RuntimeError):
                continue
            if not resolved.is_file():
                continue
            identity = str(resolved).casefold()
            if identity not in seen:
                seen.add(identity)
                matches.append({"name": str(app.get("name", requested)), "path": str(resolved)})
        if len(matches) == 1:
            return {"status": "exact", **matches[0]}
        if len(matches) > 1:
            return {"status": "ambiguous", "matches": [x["name"] for x in matches[:8]]}
        # Suggestions help the user correct speech-recognition/name mismatches;
        # they are never launched automatically.
        suggestions = []
        ranked = []
        for app in apps:
            if not isinstance(app, dict) or app.get("kind") != "exe":
                continue
            name = str(app.get("name", "")).strip()
            if not name:
                continue
            score = SequenceMatcher(None, key, _name_key(name)).ratio()
            if score >= 0.45:
                ranked.append((score, name))
        for _, name in sorted(ranked, key=lambda item: (-item[0], item[1].casefold())):
            if name.casefold() not in {item.casefold() for item in suggestions}:
                suggestions.append(name)
            if len(suggestions) == 3:
                break
        return {"status": "not_found", "matches": suggestions}

    @staticmethod
    def is_explicit_web_search(text: str) -> bool:
        """Return whether the user explicitly asked ALICE to search/research online.

        A read-only research instruction remains authoritative even if it also
        contains a safety constraint such as “do not modify files”.
        """
        request = " ".join(str(text or "").split())
        request = _WAKE_PREFIX.sub("", request, count=1)
        return bool(_WEB_SEARCH.match(request))

    @staticmethod
    def web_query(text: str) -> str | None:
        request = " ".join(str(text or "").split())
        request = _WAKE_PREFIX.sub("", request, count=1)
        match = _WEB_SEARCH.match(request)
        if match:
            query = match.group(1).strip().strip(" \t\"'")
            return query[:400] if query else None
        # Keep personal conversation and basic arithmetic on ALICE's local
        # response path; neither needs a web round trip.
        if _LOCAL_CONVERSATION.match(request) or _SIMPLE_ARITHMETIC.match(request):
            return None
        # Current, time-sensitive questions should use the internet even when
        # the user does not say "search" explicitly.
        if _FRESHNESS.search(request) and "?" in request:
            return request[:400]
        # Treat ordinary factual questions as web-enabled requests by default;
        # casual/self-referential chat remains on ALICE's normal conversation path.
        if _INFORMATION_REQUEST.search(request):
            return request[:400]
        return None

    def search_web(self, query: str, max_results: int = 5) -> list[dict]:
        response = self.web_research.search(query, max_results=max_results)
        raw = response.get("results", []) if isinstance(response, dict) else []
        clean = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url", "")).strip()
            try:
                parsed = urlparse(url)
            except ValueError:
                continue
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                continue
            title = " ".join(str(item.get("title", "")).split())[:240]
            snippet = " ".join(str(item.get("snippet", "")).split())[:600]
            if title and url:
                clean.append({"title": title, "url": url, "snippet": snippet})
            if len(clean) >= max_results:
                break
        return clean
