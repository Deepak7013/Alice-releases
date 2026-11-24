"""Public repository discovery for DEVOUR.

Search results are untrusted leads only. This adapter never clones, downloads,
or executes a candidate; the caller must choose a candidate for a later,
separately governed assimilation pass.
"""
from __future__ import annotations

import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


class DiscoveryError(RuntimeError):
    pass


class GitHubRepositoryDiscovery:
    API = "https://api.github.com/search/repositories"
    MAX_RESPONSE_BYTES = 2_000_000
    KNOWN_LICENSES = {
        "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "MPL-2.0",
        "LGPL-2.1", "LGPL-3.0", "GPL-2.0", "GPL-3.0", "AGPL-3.0",
    }

    def __init__(self, opener=None, *, timeout=15):
        self.opener = opener or urllib.request.urlopen
        self.timeout = float(timeout)

    @staticmethod
    def _count(value):
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError, OverflowError):
            return 0

    @staticmethod
    def _date(value):
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _candidate(cls, raw, now):
        if not isinstance(raw, dict):
            return None
        full_name = str(raw.get("full_name", ""))[:160]
        html_url = str(raw.get("html_url", ""))
        if (not full_name or not html_url.startswith("https://github.com/")
                or raw.get("private") is True or raw.get("disabled") is True):
            return None
        license_data = raw.get("license") if isinstance(raw.get("license"), dict) else {}
        spdx = str(license_data.get("spdx_id") or "").strip()
        updated = cls._date(raw.get("pushed_at") or raw.get("updated_at"))
        age_days = max(0, (now - updated).days) if updated else None
        stars = cls._count(raw.get("stargazers_count"))
        score = min(20.0, math.log10(stars + 1) * 5.0)
        factors = {"community_signal": round(score, 1)}
        if spdx in cls.KNOWN_LICENSES:
            score += 20
            factors["license_identified"] = 20
        else:
            factors["license_identified"] = 0
        if age_days is not None:
            recency = 15 if age_days <= 180 else 10 if age_days <= 365 else 5 if age_days <= 730 else 0
            score += recency
            factors["recent_activity"] = recency
        else:
            factors["recent_activity"] = 0
        if raw.get("archived") is True:
            score -= 30
            factors["archived_penalty"] = -30
        if raw.get("fork") is True:
            score -= 5
            factors["fork_penalty"] = -5
        return {
            "name": full_name,
            "url": html_url,
            "description": str(raw.get("description") or "")[:1000],
            "language": str(raw.get("language") or "")[:80],
            "stars": stars,
            "forks": cls._count(raw.get("forks_count")),
            "open_issues": cls._count(raw.get("open_issues_count")),
            "pushed_at": str(raw.get("pushed_at") or "")[:40],
            "archived": bool(raw.get("archived")),
            "license": {"spdx_id": spdx or None,
                        "name": str(license_data.get("name") or "")[:120],
                        "review_required": True},
            "score": round(max(0.0, min(100.0, score)), 1),
            "score_factors": factors,
            "assessment": "candidate_only; inspect provenance, architecture, dependencies, tests, license, and security before selection",
        }

    @staticmethod
    def _relevance(query, candidate):
        stop={"the","and","for","with","from","into","that","this","using","use","build","create","make","support","capability"}
        terms={term.casefold() for term in re.findall(r"[a-z0-9]{3,}",query.casefold())
               if term.casefold() not in stop}
        if not terms:
            return 0.0
        text=" ".join((candidate.get("name","") ,candidate.get("description","") ,candidate.get("language",""))).casefold()
        hits={term for term in terms if term in text}
        return round(100.0*len(hits)/len(terms),1)

    @classmethod
    def _rank_score(cls, relevance, quality):
        return round((float(relevance)*0.4)+(float(quality)*0.6),1)

    def discover(self, query, *, limit=5):
        query = " ".join(str(query or "").split())
        if len(query) < 3 or len(query) > 200 or any(ord(c) < 32 for c in query):
            raise DiscoveryError("Enter a capability description between 3 and 200 characters.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
            raise DiscoveryError("Candidate limit must be an integer from 1 to 10.")
        now = datetime.now(timezone.utc)
        ranked = {}
        total_count = 0
        incomplete = False
        for sort in ("stars", "updated"):
            params = urllib.parse.urlencode({
                "q": f"{query} is:public",
                "sort": sort,
                "order": "desc",
                "per_page": limit,
            })
            request = urllib.request.Request(
                f"{self.API}?{params}",
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "ALICE-DEVOUR",
                },
            )
            try:
                with self.opener(request, timeout=self.timeout) as response:
                    status = getattr(response, "status", 200)
                    if status != 200:
                        raise DiscoveryError(f"GitHub repository search returned HTTP {status}.")
                    payload = response.read(self.MAX_RESPONSE_BYTES + 1)
            except urllib.error.HTTPError as exc:
                raise DiscoveryError(f"GitHub repository search returned HTTP {exc.code}.") from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                raise DiscoveryError(f"GitHub repository search is unavailable: {exc}") from exc
            if len(payload) > self.MAX_RESPONSE_BYTES:
                raise DiscoveryError("GitHub repository search response exceeded the size limit.")
            try:
                data = json.loads(payload.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise DiscoveryError("GitHub repository search returned invalid JSON.") from exc
            if not isinstance(data, dict) or not isinstance(data.get("items"), list):
                raise DiscoveryError("GitHub repository search response had an unexpected shape.")
            total_count = max(total_count, self._count(data.get("total_count")))
            incomplete = incomplete or bool(data.get("incomplete_results"))
            for raw in data["items"]:
                candidate = self._candidate(raw, now)
                if candidate is None:
                    continue
                key = candidate["name"].casefold()
                if key in ranked:
                    ranked[key]["discovery_signals"].append(sort)
                else:
                    candidate["discovery_signals"] = [sort]
                    candidate["relevance_score"] = self._relevance(query,candidate)
                    candidate["discovery_score"] = self._rank_score(candidate["relevance_score"],candidate["score"])
                    ranked[key] = candidate
        candidates = list(ranked.values())
        candidates.sort(key=lambda item: (-item["discovery_score"], -item["score"],
                                          -item["stars"], item["name"].casefold()))
        for rank, candidate in enumerate(candidates, start=1):
            candidate["rank"] = rank
        return {
            "query": query,
            "source": "GitHub public repository search",
            "total_count": total_count,
            "incomplete_results": incomplete,
            "candidates": candidates[:limit],
            "policy": "ranking is advisory; no candidate is selected, downloaded, or executed by discovery itself",
        }
