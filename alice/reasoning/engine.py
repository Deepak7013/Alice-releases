from __future__ import annotations
import json, re
from dataclasses import dataclass, asdict
from alice.planning.planner import GoalPlanner
from alice.planning.models import Goal
from alice.cognitive.workspace import CognitiveWorkspaceStore

@dataclass
class VerificationResult:
    ok: bool
    score: float
    checks: list[str]
    failures: list[str]

class ReasoningEngine:
    """Executive reasoning facade: plan, retrieve context, council, verify."""
    def __init__(self, router=None, memory=None, root=None):
        self.router=router
        self.memory=memory
        self.planner=GoalPlanner()
        self.workspace=CognitiveWorkspaceStore(root=root)

    def begin_task(self, goal, *, mode="fast", constraints=None, unknowns=None, environment=None):
        return self.workspace.create(goal, mode=mode, constraints=constraints, unknowns=unknowns, environment=environment)

    def task_state(self, workspace_id=None):
        return self.workspace.get(workspace_id) if workspace_id else self.workspace.current()

    def add_evidence(self, workspace_id, evidence):
        return self.workspace.add(workspace_id, "evidence", evidence)

    def add_failure(self, workspace_id, failure):
        return self.workspace.add(workspace_id, "failures", failure)

    def add_decision(self, workspace_id, decision):
        return self.workspace.add(workspace_id, "decisions", decision)

    def complete_task(self, workspace_id, outcome, *, status="completed"):
        return self.workspace.complete(workspace_id, outcome, status=status)

    def plan(self, goal, *, context=None):
        """Plan from the goal while carrying bounded context as inert evidence."""
        if context is None:
            return self.planner.plan(goal)
        if isinstance(goal, Goal):
            merged = dict(goal.context or {})
            merged.update(dict(context))
            grounded = Goal(goal.text, tuple(goal.constraints), merged)
        else:
            grounded = Goal(str(goal), context=dict(context))
        return self.planner.plan(grounded)

    def context(self, query, limit=8):
        parts=[]
        if self.memory is not None:
            try:
                text=self.memory.context_for(query,limit=limit)
                if text: parts.append(text)
            except Exception: pass
            try:
                structured=self.memory.manager.summary(limit=min(10,limit))
                if structured and "No structured" not in structured: parts.append("STRUCTURED MEMORY:\n"+structured)
            except Exception: pass
        return "\n\n".join(parts)

    def council(self, prompt, image_path=None):
        if self.router is None: raise RuntimeError("No AI router configured")
        return self.router.council(prompt,image_path=image_path)

    def verify(self, request, answer, plan=None):
        req=str(request).strip(); ans=str(answer).strip(); checks=[]; failures=[]
        if req: checks.append("request_present")
        else: failures.append("empty_request")
        if ans: checks.append("answer_present")
        else: failures.append("empty_answer")
        if plan is not None:
            try: plan.validate(); checks.append("plan_valid")
            except Exception as e: failures.append("plan_invalid:"+str(e)[:120])
            if any(s.requires_approval for s in plan.steps): checks.append("approval_gate_detected")
        # Never certify an answer that claims completion while explicitly exposing uncertainty.
        if re.search(r"(?i)\b(done|completed|successfully)\b", ans) and re.search(r"(?i)\b(not sure|cannot verify|unverified)\b", ans):
            failures.append("completion_claim_conflicts_with_uncertainty")
        score=max(0.0,min(1.0,(len(checks)/(len(checks)+len(failures))) if checks or failures else 0.0))
        return VerificationResult(not failures,score,checks,failures)

    def verify_json(self, request, answer, plan=None):
        return json.dumps(asdict(self.verify(request,answer,plan)),indent=2)
