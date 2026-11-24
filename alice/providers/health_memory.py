"""Small persistent provider reliability ledger; evidence only, never authority."""
from __future__ import annotations
import json, os, tempfile
from pathlib import Path

class ProviderHealthMemory:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv("ALICE_PROVIDER_HEALTH_FILE", "alice_workspace/provider_health.json"))
        self.data = self._load()

    def _load(self):
        try:
            value=json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}

    def record(self, provider, *, ok, latency=None, error=""):
        row=self.data.setdefault(str(provider), {"success":0,"failure":0,"last_error":"","ema_latency":None})
        row["success" if ok else "failure"] += 1
        if latency is not None:
            old=row.get("ema_latency")
            row["ema_latency"]=float(latency) if old is None else (0.7*float(old)+0.3*float(latency))
        row["last_error"]="" if ok else str(error)[:300]
        self._save()

    def snapshot(self):
        return {k:dict(v) for k,v in self.data.items()}

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd,tmp=tempfile.mkstemp(prefix="provider_health_", suffix=".json", dir=str(self.path.parent))
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as f: json.dump(self.data,f,indent=2,sort_keys=True)
            os.replace(tmp,self.path)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
