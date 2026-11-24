"""Observe -> decide -> act -> re-observe -> verify computer-use loop."""
from __future__ import annotations
import time
from dataclasses import dataclass, field

@dataclass
class ComputerStep:
    action: dict
    before: object = None
    result: object = None
    after: object = None
    verified: bool = False
    error: str = ""

@dataclass
class ComputerRun:
    goal: str
    status: str = "pending"
    steps: list = field(default_factory=list)
    attempts: int = 0
    result: object = None

class ComputerAutonomyLoop:
    def __init__(self, controller, planner=None, verifier=None, max_steps=8, max_retries=2):
        self.controller=controller; self.planner=planner; self.verifier=verifier
        self.max_steps=int(max_steps); self.max_retries=int(max_retries)

    def run(self, goal: str):
        if not goal or len(goal)>5000: raise ValueError("invalid goal")
        run=ComputerRun(goal, status="running")
        try:
            for _ in range(self.max_steps):
                before=self.controller.observe()
                action = self.planner(goal, before, run.steps) if self.planner else None
                if action is None:
                    run.status="waiting"; run.result={"reason":"planner produced no action"}; return run
                step=ComputerStep(action, before=before); run.steps.append(step)
                try:
                    step.result=self.controller.act(action)
                    step.after=self.controller.observe()
                    step.verified = bool(self.verifier(goal, step, run) if self.verifier else True)
                    if step.verified:
                        run.status="completed"; run.result=step.after; return run
                except Exception as e:
                    step.error=str(e); run.attempts += 1
                    if run.attempts > self.max_retries: raise
            run.status="blocked"; run.result={"reason":"step limit reached"}; return run
        except Exception as e:
            run.status="failed"; run.result={"error":str(e)}; return run
