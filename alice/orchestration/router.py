from __future__ import annotations
from .graph import ResourceGraph
from .models import OrchestrationPlan, ResourceKind, RouteStep

class ResourceRouter:
    """Routes capability requirements to the safest available resource."""
    DEFAULT_PREFERENCES = {
        "browser": (ResourceKind.BROWSER, ResourceKind.PC),
        "web": (ResourceKind.BROWSER, ResourceKind.PC),
        "android": (ResourceKind.ANDROID,),
        "phone": (ResourceKind.ANDROID,),
        "desktop": (ResourceKind.PC,),
        "file": (ResourceKind.FILES, ResourceKind.PC),
        "voice": (ResourceKind.VOICE,),
        "ai": (ResourceKind.AI, ResourceKind.PC),
    }

    def __init__(self, graph: ResourceGraph):
        self.graph = graph

    def choose(self, capability: str, preferred_kind: ResourceKind | str | None = None):
        candidates = self.graph.find(capability)
        if preferred_kind is not None:
            pk = preferred_kind.value if isinstance(preferred_kind, ResourceKind) else str(preferred_kind)
            candidates.sort(key=lambda r: 0 if str(r.kind).lower().split('.')[-1] == pk.lower() else 1)
        else:
            prefs = self.DEFAULT_PREFERENCES.get(capability.lower(), ())
            ranks = {k.value if isinstance(k, ResourceKind) else str(k): i for i, k in enumerate(prefs)}
            candidates.sort(key=lambda r: ranks.get(str(r.kind).lower().split('.')[-1], 99))
        return candidates[0] if candidates else None

    def plan(self, goal: str, requirements: list[dict]) -> OrchestrationPlan:
        if not goal.strip():
            raise ValueError("goal is required")
        steps = []
        for i, req in enumerate(requirements):
            capability = str(req.get("capability", "")).strip()
            if not capability:
                raise ValueError("each requirement needs a capability")
            resource = self.choose(capability, req.get("kind"))
            if resource is None:
                raise LookupError(f"no online resource provides capability: {capability}")
            deps = tuple(req.get("depends_on", ()))
            steps.append(RouteStep(resource.resource_id, capability, str(req.get("action", "")), deps))
        return OrchestrationPlan(goal=goal, steps=steps,
                                 rationale="Selected online resources by capability and preference.")
