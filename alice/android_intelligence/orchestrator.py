from __future__ import annotations
from dataclasses import dataclass, field
from .semantics import AndroidSemanticSession

@dataclass
class AndroidTaskResult:
    status: str
    goal: str
    steps: list[dict] = field(default_factory=list)
    error: str = ""

class AndroidOrchestrator:
    """Coordinates semantic Android actions without granting new permissions."""
    def __init__(self, controller, max_steps=8):
        self.controller = controller
        self.max_steps = int(max_steps)

    def session(self, serial):
        return AndroidSemanticSession(self.controller, serial)

    def run(self, serial: str, goal: str, planner, verifier=None):
        if not goal or len(goal) > 5000:
            raise ValueError("invalid Android goal")
        session = self.session(serial)
        result = AndroidTaskResult("running", goal)
        for _ in range(self.max_steps):
            before = session.observe()
            action = planner(goal, before, result.steps)
            if action is None:
                result.status = "waiting"
                return result
            record = {"action": action, "before": before.fingerprint}
            try:
                name = action.get("name")
                if name == "click":
                    outcome = session.click(action.get("query", ""), action.get("role"))
                elif name == "launch":
                    outcome = session.launch(action.get("package", ""))
                elif name == "press":
                    outcome = session.press(action.get("key", ""))
                else:
                    raise ValueError("unsupported semantic Android action")
                record["ok"] = outcome.ok
                record["message"] = outcome.message
                if outcome.ok:
                    after = session.observe()
                    record["after"] = after.fingerprint
                    result.steps.append(record)
                    if verifier is None or verifier(goal, before, after, action):
                        result.status = "completed"
                        return result
                else:
                    result.steps.append(record)
            except Exception as exc:
                record["error"] = str(exc)
                result.steps.append(record)
                result.status = "failed"
                result.error = str(exc)
                return result
        result.status = "blocked"
        return result
