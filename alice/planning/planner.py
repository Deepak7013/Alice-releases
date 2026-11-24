
import re, secrets
from .models import Goal, Plan, PlanStep, PlanStatus

class PlanningError(ValueError):
    pass

_HIGH_RISK = re.compile(
    r"\b(send|delete|remove|purchase|buy|pay|transfer|publish|post|install|uninstall|"
    r"message|email|submit|withdraw|trade|execute)\b", re.I
)
_MEDIUM_RISK = re.compile(r"\b(change|edit|modify|update|create|move|rename|upload|download)\b", re.I)

class GoalPlanner:
    """Deterministic goal-to-plan compiler.

    It does not execute actions, grant permissions, or bypass approval gates.
    """

    def __init__(self, action_catalog=None):
        self.action_catalog = dict(action_catalog or {})

    def _risk(self, text):
        if _HIGH_RISK.search(text): return "high"
        if _MEDIUM_RISK.search(text): return "medium"
        return "low"

    def _step(self, i, action, deps=(), rationale=""):
        risk=self._risk(action)
        return PlanStep(
            step_id=f"step_{i}",
            action=action.strip(),
            depends_on=list(deps),
            consequence=risk,
            requires_approval=risk in {"high","critical"},
            rationale=rationale or "Required to advance the goal."
        )

    def plan(self, goal: Goal | str) -> Plan:
        if isinstance(goal, str): goal=Goal(goal)
        text=goal.text.strip()
        lower=text.lower()
        steps=[]
        assumptions=[]
        unresolved=[]

        # Explicit multi-step syntax is deterministic and transparent.
        parts=[p.strip() for p in re.split(r"\s*(?:->|;|\n)\s*", text) if p.strip()]
        if len(parts) > 1:
            for i,part in enumerate(parts,1):
                steps.append(self._step(i, part, [f"step_{i-1}"] if i>1 else []))
        elif any(k in lower for k in ("research", "find out", "look up", "investigate")):
            steps=[
                self._step(1,"Research the requested topic using available sources.",
                           rationale="Gather evidence before drawing conclusions."),
                self._step(2,"Summarize findings and state uncertainty.",
                           ["step_1"],"Separate evidence from assumptions.")
            ]
        elif any(k in lower for k in ("build", "create a project", "make a website", "develop")):
            steps=[
                self._step(1,"Clarify requirements and constraints from the goal.",
                           rationale="Avoid implementing an underspecified request."),
                self._step(2,"Design the smallest implementation that satisfies the requirements.",
                           ["step_1"]),
                self._step(3,"Build the implementation in the designated workspace.",
                           ["step_2"]),
                self._step(4,"Run tests and verify the result against the requirements.",
                           ["step_3"]),
            ]
        elif any(k in lower for k in ("connect", "control", "use my phone", "use my laptop")):
            steps=[
                self._step(1,"Discover available devices matching the request.",
                           rationale="Discovery must occur before selection or authorization."),
                self._step(2,"Select the requested device without granting permissions.",
                           ["step_1"]),
                self._step(3,"Request only the minimum permissions needed for the task.",
                           ["step_2"]),
                self._step(4,"Execute the requested device action after authorization.",
                           ["step_3"]),
                self._step(5,"Verify the action outcome and report evidence.",
                           ["step_4"]),
            ]
        else:
            steps=[
                self._step(1,"Interpret the goal and identify required capabilities.",
                           rationale="Establish what Alice must actually do."),
                self._step(2,"Execute the lowest-risk available actions needed for the goal.",
                           ["step_1"]),
                self._step(3,"Verify the outcome against the original goal.",
                           ["step_2"]),
            ]
            assumptions.append("The required capability is available to Alice.")
            unresolved.append("If the goal requires a consequential action, explicit approval remains required.")

        world_context = goal.context.get("world_model") if isinstance(goal.context, dict) else None
        if isinstance(world_context, dict) and world_context.get("trust") == "observation_only":
            assumptions.append("Attached WorldModel data is observational context, not an instruction source.")
            unresolved.append("Refresh stale observations and independently verify current state before consequential actions.")

        plan=Plan("plan_"+secrets.token_hex(8),goal,steps,PlanStatus.READY,assumptions,unresolved)
        plan.validate()
        return plan
