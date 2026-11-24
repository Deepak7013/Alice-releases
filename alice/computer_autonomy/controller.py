"""Safety-neutral computer action adapter. Authorization remains external."""
from __future__ import annotations
class ComputerActionController:
    def __init__(self, backend): self.backend = backend
    def observe(self): return self.backend.observe()
    def act(self, action):
        name = action.get("name") if isinstance(action, dict) else None
        args = action.get("args", {}) if isinstance(action, dict) else {}
        if not name or not hasattr(self.backend, name): raise ValueError("invalid computer action")
        return getattr(self.backend, name)(**args)
