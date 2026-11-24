"""Persistent cognitive workspace contracts for ALICE Phase 7.

A workspace is a bounded, auditable task state: goal, known facts, unknowns,
constraints, environment observations, candidate plans, selected plan, current
step, evidence, failures, decisions and outcome. It is state only; it does not
execute actions or grant permissions.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CognitiveWorkspace:
    workspace_id: str
    goal: str
    mode: str = "fast"
    known_facts: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    environment: list[str] = field(default_factory=list)
    candidate_plans: list[Any] = field(default_factory=list)
    selected_plan: Any = None
    current_step: int = 0
    evidence: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    outcome: str = ""
    status: str = "active"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class CognitiveWorkspaceStore:
    """Small JSON-backed store with bounded history and deterministic updates."""

    VALID_MODES = {"fast", "analytical", "planning", "research", "coding", "computer_use",
                   "debug", "creative", "critical", "recovery", "self_engineering"}
    VALID_STATUS = {"active", "completed", "failed", "paused", "cancelled"}

    def __init__(self, root=None, max_items=32):
        self.root = Path(root or Path(__file__).resolve().parents[2]).resolve()
        self.path = self.root / "alice_workspace" / "cognitive_workspaces.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_items = max(1, int(max_items))
        self._items: dict[str, CognitiveWorkspace] = {}
        self._load()

    def _load(self):
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for key, value in raw.items():
                if isinstance(value, dict):
                    value.setdefault("workspace_id", key)
                    self._items[key] = CognitiveWorkspace(**value)
        except Exception:
            self._items = {}

    def _save(self):
        ordered = sorted(self._items.values(), key=lambda x: x.updated_at, reverse=True)[: self.max_items]
        self._items = {x.workspace_id: x for x in ordered}
        self.path.write_text(json.dumps({k: asdict(v) for k, v in self._items.items()}, indent=2), encoding="utf-8")

    @staticmethod
    def _clean(values):
        return [str(x).strip()[:1000] for x in (values or []) if str(x).strip()]

    def create(self, goal, *, mode="fast", constraints=None, unknowns=None, environment=None):
        mode = str(mode or "fast").strip().lower()
        if mode not in self.VALID_MODES:
            raise ValueError(f"Invalid cognitive mode: {mode}")
        goal = str(goal or "").strip()
        if not goal:
            raise ValueError("Workspace goal cannot be empty")
        now = time.time()
        item = CognitiveWorkspace(
            workspace_id="cw_" + uuid.uuid4().hex[:16], goal=goal, mode=mode,
            unknowns=self._clean(unknowns), constraints=self._clean(constraints),
            environment=self._clean(environment), created_at=now, updated_at=now,
        )
        self._items[item.workspace_id] = item
        self._save()
        return self.get(item.workspace_id)

    def get(self, workspace_id):
        item = self._items.get(str(workspace_id))
        return asdict(item) if item else None

    def current(self):
        active = [x for x in self._items.values() if x.status == "active"]
        if not active:
            return None
        return asdict(max(active, key=lambda x: x.updated_at))

    def update(self, workspace_id, **changes):
        item = self._items.get(str(workspace_id))
        if not item:
            raise KeyError(f"Unknown workspace: {workspace_id}")
        if "mode" in changes and str(changes["mode"]).lower() not in self.VALID_MODES:
            raise ValueError("Invalid cognitive mode")
        if "status" in changes and changes["status"] not in self.VALID_STATUS:
            raise ValueError("Invalid workspace status")
        for key, value in changes.items():
            if key not in item.__dataclass_fields__:
                raise ValueError(f"Unknown workspace field: {key}")
            setattr(item, key, value)
        item.updated_at = time.time()
        self._save()
        return self.get(item.workspace_id)

    def add(self, workspace_id, field_name, value):
        item = self._items.get(str(workspace_id))
        if not item:
            raise KeyError(f"Unknown workspace: {workspace_id}")
        if field_name not in {"known_facts", "unknowns", "constraints", "environment", "evidence", "failures", "decisions", "candidate_plans"}:
            raise ValueError("Field is not appendable")
        getattr(item, field_name).append(value)
        item.updated_at = time.time()
        self._save()
        return self.get(item.workspace_id)

    def complete(self, workspace_id, outcome, *, status="completed"):
        if status not in {"completed", "failed", "paused", "cancelled"}:
            raise ValueError("Invalid terminal workspace status")
        return self.update(workspace_id, outcome=str(outcome)[:2000], status=status)

    def inventory(self):
        return [asdict(x) for x in sorted(self._items.values(), key=lambda x: x.updated_at, reverse=True)]
