"""Persistent, privacy-conscious experience store for Alice.

Stores workflow patterns, outcomes, tool reliability and lessons. Secrets are filtered;
raw screenshots, credentials and full model transcripts are never persisted here.
"""
import hashlib, json, re, time
from pathlib import Path
from ..core.atomic_json import atomic_write_json

SECRET = re.compile(r"(?i)(api[_-]?key|token|password|secret|authorization|cookie)\s*[:=]")

class ExperienceStore:
    def __init__(self, root=None):
        root = Path(root or Path(__file__).resolve().parents[2])
        self.path = root / "alice_workspace" / "experience.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self):
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            d.setdefault("workflows", []); d.setdefault("tools", {}); d.setdefault("lessons", [])
            return d
        except Exception:
            return {"workflows": [], "tools": {}, "lessons": []}

    def _save(self):
        atomic_write_json(self.path, self.data)

    @staticmethod
    def signature(request):
        normalized = re.sub(r"\s+", " ", request.strip().lower())
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def recall(self, request, limit=5):
        sig = self.signature(request)
        exact = [x for x in self.data["workflows"] if x.get("signature") == sig]
        if exact:
            return sorted(exact, key=lambda x: x.get("score", 0), reverse=True)[:limit]
        words = set(re.findall(r"[a-z0-9_]{4,}", request.lower()))
        scored=[]
        for x in self.data["workflows"]:
            overlap=len(words & set(x.get("keywords", [])))
            if overlap: scored.append((overlap + x.get("score",0)*0.05, x))
        return [x for _,x in sorted(scored, key=lambda z:z[0], reverse=True)[:limit]]

    def record(self, request, tool_sequence, success, summary="", lessons=None):
        safe_summary = str(summary)[:700]
        if SECRET.search(safe_summary): safe_summary = "[redacted]"
        keywords = list(dict.fromkeys(re.findall(r"[a-z0-9_]{4,}", request.lower())))[:30]
        item = {
            "signature": self.signature(request), "request": request[:500],
            "keywords": keywords, "tools": list(dict.fromkeys(tool_sequence))[:50],
            "success": bool(success), "score": 1.0 if success else -0.5,
            "summary": safe_summary, "time": time.time()
        }
        self.data["workflows"].append(item)
        self.data["workflows"] = self.data["workflows"][-300:]
        for tool in set(tool_sequence):
            t=self.data["tools"].setdefault(tool,{"uses":0,"successes":0,"failures":0})
            t["uses"] += 1; t["successes" if success else "failures"] += 1
        for lesson in lessons or []:
            if lesson and not SECRET.search(lesson):
                self.data["lessons"].append({"text":str(lesson)[:500],"time":time.time()})
        self.data["lessons"] = self.data["lessons"][-200:]
        self._save()
        return item

    def context(self, request, limit=5):
        recalled=self.recall(request, limit)
        if not recalled: return "No prior experience matches this task."
        compact=[]
        for x in recalled:
            compact.append({"request":x["request"],"success":x["success"],"tools":x["tools"],"summary":x["summary"]})
        return json.dumps(compact, ensure_ascii=False)

    def stats(self):
        total=len(self.data["workflows"])
        good=sum(1 for x in self.data["workflows"] if x.get("success"))
        return {"workflows":total,"successful":good,"success_rate":round(good/total,3) if total else 0,"tools":self.data["tools"]}
