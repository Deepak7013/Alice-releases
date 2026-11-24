
from __future__ import annotations
from dataclasses import dataclass
from .adapter import VisionAdapter
from .models import VisualObservation, VisualTarget

@dataclass
class VisualActionLoop:
    controller: object
    vision: VisionAdapter
    max_recovery_attempts: int = 2

    def observe(self, goal: str) -> VisualObservation:
        frame = self.vision.capture(self.controller)
        return self.vision.analyze(frame, goal)

    def _changed(self, before, after) -> bool:
        return bool(before.frame.fingerprint != after.frame.fingerprint)

    def click_target(self, goal: str, target_name: str,
                     role: str | None = None) -> dict:
        attempts = 0
        observation = self.observe(goal)
        while attempts <= self.max_recovery_attempts:
            target = observation.find(target_name, role)
            if target is None or not target.bounds:
                attempts += 1
                if attempts > self.max_recovery_attempts:
                    return {"ok": False, "reason": "target_not_found",
                            "attempts": attempts}
                observation = self.observe(goal)
                continue

            x, y, w, h = target.bounds
            action = self._click_bounds(x, y, w, h)
            if not action.ok:
                attempts += 1
                observation = self.observe(goal)
                continue

            after = self.observe(goal)
            if self._changed(observation, after):
                return {"ok": True, "attempts": attempts + 1,
                        "verified": True, "target": target_name}

            # Click happened but expected visual state did not change.
            attempts += 1
            if attempts > self.max_recovery_attempts:
                return {"ok": False, "reason": "verification_failed",
                        "attempts": attempts}
            observation = after

        return {"ok": False, "reason": "recovery_exhausted",
                "attempts": attempts}

    def _click_bounds(self, x, y, w, h):
        if hasattr(self.controller, "click"):
            return self.controller.click(x + w // 2, y + h // 2)
        if hasattr(self.controller, "tap"):
            return self.controller.tap(x + w // 2, y + h // 2)
        from alice.computer.models import ActionResult
        return ActionResult(False, "click", "controller lacks click/tap")
