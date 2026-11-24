"""ALICE upgrade lifecycle audit trail.

Records bounded, non-secret checkpoints for a self-update transaction so a failed
relaunch can be diagnosed and a successful upgrade can be proven. This module
never stores credentials and never grants upgrade authority.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

_SECRET = re.compile(r"(?i)(api[_-]?key|token|password|secret|authorization|credential)")


class UpgradeAudit:
    VERSION = "v3.53.0"
    MAX_EVENTS = 80

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.path = self.root / "alice_workspace" / "runtime" / "upgrade_audit.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe(value, limit=600):
        text = str(value or "")
        if _SECRET.search(text):
            return "[redacted]"
        return text[:limit]

    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("events"), list):
                return data
        except Exception:
            pass
        return {"version": self.VERSION, "events": []}

    def record(self, stage, *, ok=True, version="", detail="", digest=""):
        data = self._load()
        event = {
            "time": time.time(),
            "stage": self._safe(stage, 120),
            "ok": bool(ok),
            "version": self._safe(version, 80),
            "detail": self._safe(detail),
        }
        if digest:
            event["digest"] = hashlib.sha256(str(digest).encode()).hexdigest()[:16]
        data["events"] = (data.get("events", []) + [event])[-self.MAX_EVENTS:]
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)
        return event

    def summary(self):
        data = self._load()
        events = data.get("events", [])
        return {
            "version": self.VERSION,
            "event_count": len(events),
            "last_stage": events[-1].get("stage") if events else None,
            "last_ok": events[-1].get("ok") if events else None,
            "events": events[-12:],
        }
