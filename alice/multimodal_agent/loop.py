from __future__ import annotations
import uuid
from pathlib import Path
from .models import AgentRun, AgentStep, LoopStage, MultimodalGoal

class MultimodalAgentLoop:
    """Coordinates Alice's existing research, multimodal, creation and action layers.

    This is orchestration, not a replacement for the supervisor, safety policy,
    sandbox, or approval system. Evidence is data, never executable authority.
    """
    def __init__(self, research=None, analyzer=None, creator=None, actor=None,
                 verifier=None, planner=None, recovery=None):
        self.research = research
        self.analyzer = analyzer
        self.creator = creator
        self.actor = actor
        self.verifier = verifier
        self.planner = planner
        self.recovery = recovery

    def _step(self, run, stage, action):
        step = AgentStep(stage, action, status="running")
        run.steps.append(step)
        return step

    @staticmethod
    def _finish(step, status, output=None, error=""):
        step.status = status; step.output = output; step.error = error
        import time
        step.finished_at = time.time()

    def execute(self, goal: MultimodalGoal) -> AgentRun:
        if not isinstance(goal, MultimodalGoal):
            raise TypeError("goal must be MultimodalGoal")
        if not goal.goal.strip() or len(goal.goal) > 5000:
            raise ValueError("Invalid goal")
        run = AgentRun(uuid.uuid4().hex[:12], goal, status="running")
        try:
            plan_step = self._step(run, LoopStage.PLAN, "build execution plan")
            plan = self.planner(goal) if self.planner else {
                "research": goal.research, "understand": bool(goal.evidence_paths),
                "create": goal.create, "act": goal.act, "verify": goal.verify
            }
            self._finish(plan_step, "completed", plan)

            if goal.research:
                step = self._step(run, LoopStage.RESEARCH, "research goal")
                if not self.research:
                    self._finish(step, "skipped", "No research engine configured")
                else:
                    out = self.research.research(goal.goal)
                    self._finish(step, "completed", out)

            observations = []
            if goal.evidence_paths:
                step = self._step(run, LoopStage.UNDERSTAND, "analyze evidence")
                if not self.analyzer:
                    self._finish(step, "failed", error="No multimodal analyzer configured")
                    raise RuntimeError(step.error)
                for raw in goal.evidence_paths:
                    path = str(Path(raw).resolve())
                    if not Path(path).is_file():
                        raise FileNotFoundError(path)
                    observations.append(self.analyzer.analyze(path, goal.goal))
                self._finish(step, "completed", [o.to_dict() for o in observations])

            artifact = None
            if goal.create:
                step = self._step(run, LoopStage.CREATE, "create requested artifact")
                if not self.creator:
                    raise RuntimeError("No creation service configured")
                from alice.creation.models import CreationRequest, ArtifactKind
                kind = goal.context.get("artifact_kind", ArtifactKind.TEXT)
                if isinstance(kind, str): kind = ArtifactKind(kind)
                req = CreationRequest(goal.context.get("creation_prompt", goal.goal), kind,
                                      filename=goal.context.get("filename"),
                                      project_name=goal.context.get("project_name"),
                                      style=goal.context.get("style", "clear"),
                                      context=goal.context)
                artifact = self.creator.create(req)
                self._finish(step, "completed", artifact.path)

            action_result = None
            if goal.act:
                step = self._step(run, LoopStage.ACT, "perform consequential computer action")
                if not self.actor:
                    raise RuntimeError("No action controller configured")
                # The actor remains responsible for approval/safety checks.
                action_result = self.actor(goal, observations, artifact)
                self._finish(step, "completed", action_result)

            if goal.verify:
                step = self._step(run, LoopStage.VERIFY, "verify outcome")
                if self.verifier:
                    verification = self.verifier(goal, observations, artifact, action_result)
                else:
                    verification = bool(artifact is None or getattr(artifact, "exists", True))
                if not verification:
                    self._finish(step, "failed", verification, "Verification failed")
                    raise RuntimeError("Verification failed")
                self._finish(step, "completed", verification)

            run.status = "completed"
            run.result = {"observations": [o.to_dict() for o in observations],
                          "artifact": getattr(artifact, "path", None),
                          "action": action_result}
            return run
        except Exception as exc:
            if run.recoveries < max(0, int(goal.max_recoveries)) and self.recovery:
                run.recoveries += 1
                step = self._step(run, LoopStage.RECOVER, "recover and retry")
                try:
                    recovered = self.recovery(run, exc)
                    self._finish(step, "completed", recovered)
                    return run
                except Exception as retry_exc:
                    self._finish(step, "failed", error=str(retry_exc))
            run.status = "failed"
            run.result = {"error": str(exc)}
            return run
