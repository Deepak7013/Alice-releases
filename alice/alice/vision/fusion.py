
from __future__ import annotations
from .models import VisualObservation, VisualTarget
from .hierarchy import UIHierarchyAdapter, HierarchyNode

class EvidenceFusion:
    """Merge native hierarchy evidence with vision-model evidence.

    Native accessibility/UI hierarchy wins when names/roles overlap and
    its bounds are available; vision fills gaps that native APIs cannot see.
    """
    def __init__(self, hierarchy_adapter=None):
        self.hierarchy = hierarchy_adapter or UIHierarchyAdapter()

    def merge(self, vision: VisualObservation,
              hierarchy: HierarchyNode | None = None) -> VisualObservation:
        native = self.hierarchy.targets(hierarchy) if hierarchy else []
        merged = list(native)
        index = {(t.name.casefold(), t.role) for t in native if t.name}
        for target in vision.targets:
            key = (target.name.casefold(), target.role)
            if key not in index:
                merged.append(target)
                index.add(key)
        confidence = max(
            [vision.confidence] +
            [t.confidence for t in merged] +
            [0.0]
        )
        text = vision.text
        return VisualObservation(vision.frame, merged, text, confidence)
