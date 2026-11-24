"""Small durable JSON store for goals and agency observations."""
from __future__ import annotations
import json, threading
from pathlib import Path
from typing import Any

class AgencyStore:
    def __init__(self, root=None):
        self.root=Path(root or Path(__file__).resolve().parents[2])
        self.path=self.root/"alice_workspace"/"agency"/"state.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock=threading.RLock(); self.data=self._load()
    def _load(self):
        try: return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception: return {"goals":{},"observations":[]}
    def _save(self):
        tmp=self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data,indent=2,ensure_ascii=False,default=str),encoding="utf-8")
        tmp.replace(self.path)
    def put_goal(self, goal):
        with self._lock:
            self.data["goals"][goal.id]=goal.to_dict(); self._save()
        return self.data["goals"][goal.id]
    def get_goal(self, goal_id): return self.data["goals"].get(goal_id)
    def goals(self, status=None):
        vals=list(self.data["goals"].values())
        return [g for g in vals if status is None or g.get("status")==status]
    def delete_goal(self, goal_id):
        with self._lock:
            existed=self.data["goals"].pop(goal_id,None) is not None; self._save()
        return existed
    def add_observation(self, observation):
        with self._lock:
            self.data["observations"].append(observation.__dict__)
            self.data["observations"]=self.data["observations"][-500:]
            self._save()
        return observation.__dict__
    def observations(self, limit=50): return self.data["observations"][-limit:]
