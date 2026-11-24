from __future__ import annotations
from typing import Any, Callable
from .graph import ResourceGraph
from .models import OrchestrationPlan, OrchestrationResult, Resource
from .router import ResourceRouter
from .sync import StateSynchronizer

class CrossDeviceOrchestrator:
    """Coordinates PC, Android, browser, file, voice and AI resources.

    Adapters are injected by the application. This layer only routes and coordinates;
    existing safety/approval systems remain authoritative for consequential actions.
    """
    def __init__(self, graph: ResourceGraph | None = None, synchronizer: StateSynchronizer | None = None):
        self.graph = graph or ResourceGraph()
        self.sync = synchronizer or StateSynchronizer()
        self.router = ResourceRouter(self.graph)
        self.adapters: dict[str, Any] = {}

    def register(self, resource: Resource, adapter: Any = None) -> None:
        self.graph.register(resource)
        if adapter is not None:
            self.adapters[resource.resource_id] = adapter

    def discover(self, resources: list[Resource]) -> list[dict]:
        for resource in resources:
            self.graph.register(resource)
        return self.graph.snapshot()

    def plan(self, goal: str, requirements: list[dict]) -> OrchestrationPlan:
        return self.router.plan(goal, requirements)

    def execute(self, plan: OrchestrationPlan,
                action_runner: Callable[[Resource, str, str, dict], Any] | None = None,
                verifier: Callable[[Resource, dict, Any], bool] | None = None) -> OrchestrationResult:
        result = OrchestrationResult(True, plan.goal)
        for index, step in enumerate(plan.steps):
            if any(dep < 0 or dep >= index or dep not in {x["index"] for x in result.completed_steps}
                   for dep in step.depends_on):
                return self._fail(result, index, "step dependency not completed")
            resource = self.graph.get(step.resource_id)
            if resource is None or not resource.online:
                return self._fail(result, index, f"resource unavailable: {step.resource_id}")
            adapter = self.adapters.get(resource.resource_id)
            before = self.sync.get(resource.resource_id)
            context = before.state if before else {}
            try:
                if action_runner:
                    outcome = action_runner(resource, step.capability, step.action, context)
                elif adapter is not None and hasattr(adapter, "execute"):
                    outcome = adapter.execute(step.capability, step.action, context)
                else:
                    outcome = {"ok": True, "planned": True, "resource": resource.resource_id}
                ok = outcome.get("ok", True) if isinstance(outcome, dict) else bool(outcome)
                if not ok:
                    return self._fail(result, index, f"action failed on {resource.resource_id}", outcome)
                if verifier and not verifier(resource, context, outcome):
                    return self._fail(result, index, f"verification failed on {resource.resource_id}", outcome)
                state = outcome.get("state", {}) if isinstance(outcome, dict) else {}
                self.sync.update(resource.resource_id, state)
                result.completed_steps.append({"index": index, "resource": resource.resource_id,
                                               "capability": step.capability, "outcome": outcome})
            except Exception as exc:
                return self._fail(result, index, str(exc))
        return result

    @staticmethod
    def _fail(result, index, error, outcome=None):
        result.ok = False
        result.failed_step = index
        result.error = error
        if outcome is not None:
            result.completed_steps.append({"index": index, "outcome": outcome, "ok": False})
        result.synchronized = False
        return result
