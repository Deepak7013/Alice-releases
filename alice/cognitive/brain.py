from __future__ import annotations
"""ALICE v3.50 Unified Brain Kernel.

This is the first explicit integration layer for ALICE's own cognitive
architecture. It composes executive intent, verified knowledge, cognitive
workspace, capability self-model and bounded planning into one inspectable
brain state. It is deliberately non-executing: action execution remains behind
ALICE's existing approval/action stack.
"""
from dataclasses import dataclass, asdict, field
from typing import Any

from .executive import ExecutiveController, TaskIntent
from .context import KnowledgeContextBuilder, ExecutiveKnowledgeContext
from .workspace import CognitiveWorkspaceStore
from alice.planning.planner import GoalPlanner
from .long_horizon import LongHorizonStore
from .continuity import ExecutiveContinuity


@dataclass
class BrainState:
    request: str
    intent: str
    workspace_id: str | None = None
    mode: str = "fast"
    verified_knowledge: list[Any] = field(default_factory=list)
    world_context: dict[str, Any] = field(default_factory=dict)
    candidate_plan: Any = None
    capability_gaps: list[str] = field(default_factory=list)
    available_capabilities: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    approval_required: bool = False
    analysis_only: bool = False
    no_execution: bool = False
    next_stage: str = "reason"
    confidence: float = 0.0
    related_long_goals: list[dict[str, Any]] = field(default_factory=list)
    next_long_action: str | None = None

    def to_dict(self):
        return asdict(self)


class BrainKernel:
    """Persistent cognitive integration facade; no side effects beyond workspace state."""
    VERSION = "v3.50.0"
    MODES = {"fast", "analytical", "planning", "research", "coding", "computer_use",
             "debug", "creative", "critical", "recovery", "self_engineering"}

    def __init__(self, *, user_model=None, learning_store=None, world_model=None,
                 capability_manager=None, workspace_store=None, long_horizon=None, executive=None):
        self.executive = executive or ExecutiveController()
        self.context = KnowledgeContextBuilder(user_model, learning_store, world_model)
        self.workspace = workspace_store or CognitiveWorkspaceStore()
        self.capabilities = capability_manager
        self.long_horizon = long_horizon or LongHorizonStore(root=getattr(self.workspace, "root", None))
        self.planner = GoalPlanner()
        self.continuity = ExecutiveContinuity(self.long_horizon)

    @staticmethod
    def _mode(intent: TaskIntent, requested: str | None) -> str:
        if requested and requested in BrainKernel.MODES:
            return requested
        return {
            TaskIntent.HYPOTHETICAL: "critical",
            TaskIntent.PLANNING: "planning",
            TaskIntent.SELF_ENGINEERING: "self_engineering",
            TaskIntent.DEVOUR: "research",
            TaskIntent.UPDATE: "self_engineering",
            TaskIntent.DIAGNOSTIC: "debug",
            TaskIntent.ACTION: "computer_use",
        }.get(intent, "fast")

    def _knowledge_items(self, ctx: ExecutiveKnowledgeContext):
        return list(ctx.user_facts) + list(ctx.lessons)

    def think(self, request: str, *, mode: str | None = None,
              constraints: list[str] | None = None,
              environment: list[str] | None = None,
              create_workspace: bool = True) -> BrainState:
        request = str(request or "").strip()
        if not request:
            raise ValueError("request is required")
        intent = self.executive.classify(request)
        selected_mode = self._mode(intent, mode)
        exec_ctx = self.executive.prepare(request, constraints=constraints)
        knowledge = self.context.build(request)

        wid = None
        if create_workspace:
            ws = self.workspace.create(
                request, mode=selected_mode,
                constraints=list(exec_ctx.constraints),
                environment=list(environment or []),
            )
            wid = ws["workspace_id"]
            for item in self._knowledge_items(knowledge)[:16]:
                label = getattr(item, "key", None) or (item.get("key") if isinstance(item, dict) else None)
                value = getattr(item, "value", None) or (item.get("value") if isinstance(item, dict) else None)
                if label and value:
                    self.workspace.add(wid, "known_facts", f"{label}: {value}")
            if knowledge.world:
                self.workspace.add(wid, "environment", "world_model_context_available")

        plan = None
        if intent not in {TaskIntent.CONVERSATION, TaskIntent.MEMORY, TaskIntent.DIAGNOSTIC}:
            try:
                plan = self.planner.plan(request)
            except Exception:
                plan = None

        gaps = []
        available = []
        if self.capabilities is not None:
            try:
                self_model = self.capabilities.self_model()
                available = list(self_model.get("available", []))
                gaps = list(self.capabilities.gap(request, available))
            except Exception:
                pass

        if wid:
            if plan is not None:
                self.workspace.update(wid, candidate_plans=[plan.to_dict() if hasattr(plan, "to_dict") else str(plan)])
            if gaps:
                self.workspace.add(wid, "unknowns", "capability gaps: " + ", ".join(gaps))
            self.workspace.add(wid, "decisions", f"intent={intent.value}; mode={selected_mode}")

        next_stage = "answer"
        if intent == TaskIntent.HYPOTHETICAL:
            next_stage = "analyze"
        elif intent in {TaskIntent.ACTION, TaskIntent.SELF_ENGINEERING, TaskIntent.DEVOUR, TaskIntent.UPDATE}:
            next_stage = "authorize" if exec_ctx.approval_required else "execute"
        elif plan is not None:
            next_stage = "verify_plan"

        related_goals = self.resume_goals(request)
        continuity = self.continuity.resume(request)
        knowledge_count = len(self._knowledge_items(knowledge))
        confidence = 0.5
        if knowledge_count: confidence += 0.1
        if plan is not None: confidence += 0.2
        if not gaps: confidence += 0.1
        if intent == TaskIntent.HYPOTHETICAL: confidence += 0.1

        return BrainState(
            request=request,
            intent=intent.value,
            workspace_id=wid,
            mode=selected_mode,
            verified_knowledge=self._knowledge_items(knowledge)[:16],
            world_context=knowledge.world,
            candidate_plan=plan.to_dict() if hasattr(plan, "to_dict") else plan,
            capability_gaps=gaps,
            available_capabilities=available,
            constraints=list(exec_ctx.constraints),
            approval_required=exec_ctx.approval_required,
            analysis_only="analysis_only" in exec_ctx.constraints,
            no_execution="no_execution" in exec_ctx.constraints,
            next_stage=next_stage,
            confidence=min(1.0, confidence),
            related_long_goals=related_goals,
            next_long_action=continuity.next_action,
        )

    def resume_goals(self, request: str, limit=4):
        return self.long_horizon.find(request, limit=limit)

    def continuity_decision(self, request: str, limit=4):
        return self.continuity.resume(request, limit=limit)

    def inspect(self, request: str, **kwargs):
        """Alias for a read-only cognitive pass."""
        return self.think(request, **kwargs).to_dict()
