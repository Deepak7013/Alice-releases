
from __future__ import annotations
import hashlib
from pathlib import Path
from .models import VisualFrame, VisualObservation

class VisionAdapter:
    """Backend-neutral visual understanding interface.

    A real deployment can attach a local vision model, OpenAI vision model,
    Anthropic/Gemini/etc. The computer-control layer only consumes the
    normalized observation.
    """

    def capture(self, controller) -> VisualFrame:
        if hasattr(controller, "screenshot"):
            result = controller.screenshot()
            if isinstance(result, VisualFrame):
                return result
            if isinstance(result, (str, Path)):
                p = Path(result)
                data = p.read_bytes() if p.exists() else str(result).encode()
                return VisualFrame(
                    platform=getattr(controller, "platform", "unknown"),
                    image_path=str(p),
                    fingerprint=hashlib.sha256(data).hexdigest(),
                )
        state = controller.observe()
        return VisualFrame(
            platform=state.platform,
            fingerprint=state.fingerprint,
            metadata={"screen_state": state},
        )

    def analyze(self, frame: VisualFrame, goal: str) -> VisualObservation:
        # Base adapter deliberately returns no guessed targets.
        # Production adapters override this using a vision model.
        return VisualObservation(frame=frame)
