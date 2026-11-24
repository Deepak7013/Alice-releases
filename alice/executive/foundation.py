"""Unified executive foundation: intent, workspace, capability and completion gates."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any
from alice.cognitive.executive import ExecutiveController, TaskIntent
from alice.cognitive.workspace import CognitiveWorkspaceStore
from alice.self_model import SelfModelSnapshot

@dataclass
class ExecutiveDecision:
    request: str
    intent: str
    workspace_id: str | None
    executable: bool
    approval_required: bool
    capability_gap: dict[str, Any] | None
    constraints: list[str]

class ExecutiveFoundation:
    """Side-effect-bounded executive facade; actual actions remain elsewhere."""
    def __init__(self, root=None, controller=None, workspace=None, capabilities=None):
        self.controller = controller or ExecutiveController()
        self.workspace = workspace or CognitiveWorkspaceStore(root)
        self.capabilities = capabilities

    def prepare(self, request: str, *, mode="fast", capability: str | None = None, constraints=None):
        ctx = self.controller.prepare(request, constraints=constraints)
        wid = None
        if ctx.intent not in {TaskIntent.CONVERSATION, TaskIntent.HYPOTHETICAL}:
            w = self.workspace.create(request, mode=mode, constraints=ctx.constraints)
            wid = w["workspace_id"]
        gap = None
        if capability and self.capabilities is not None:
            gap = SelfModelSnapshot.build(self.capabilities).capability_gap(capability)
        executable = self.controller.can_execute(ctx) and not (gap and gap.get("gap"))
        return ExecutiveDecision(request, ctx.intent.value, wid, executable, self.controller.requires_user_approval(ctx), gap, list(ctx.constraints))

    @staticmethod
    def completion_ready(verification: Any) -> bool:
        if isinstance(verification, dict): return bool(verification.get("ok"))
        return bool(getattr(verification, "ok", False))

    def to_dict(self, decision: ExecutiveDecision): return asdict(decision)
