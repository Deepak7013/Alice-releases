from __future__ import annotations
"""Bounded proactive task support.

Proactivity is opt-in and uses the existing persistent scheduler. ALICE never
creates a background job merely because a topic appeared in conversation.
"""
from pathlib import Path
import json, time

class ProactiveManager:
    def __init__(self, runtime=None, root=None):
        self.runtime=runtime
        self.root=Path(root or Path(__file__).resolve().parents[2])
        self.path=self.root/"alice_workspace"/"proactive"/"preferences.json"
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.data=self._load()
    def _load(self):
        try:return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:return {"enabled":False,"jobs":[]}
    def _save(self):self.path.write_text(json.dumps(self.data,indent=2),encoding="utf-8")
    def enabled(self):return bool(self.data.get("enabled"))
    def set_enabled(self,enabled):
        self.data["enabled"]=bool(enabled); self._save(); return self.enabled()
    def describe(self):
        return {"enabled":self.enabled(),"jobs":list(self.data.get("jobs",[]))}
    def add_job(self,name,interval_seconds,request):
        if not self.runtime: raise RuntimeError("Runtime scheduler unavailable")
        if not self.enabled(): raise PermissionError("Proactive mode is disabled; enable it explicitly first")
        job=self.runtime.scheduler.add(name,int(interval_seconds),request)
        self.data.setdefault("jobs",[]).append({"id":job["id"],"name":name,"request":request,"created":time.time()})
        self._save(); return job
