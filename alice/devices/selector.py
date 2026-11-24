from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from .discovery import DeviceCandidate


class DeviceSelectionError(LookupError):
    """Raised when a requested device cannot be selected unambiguously."""


class DeviceSelector:
    """Select a discovered device without changing its authorization state."""

    @staticmethod
    def select(
        candidates: Iterable[DeviceCandidate],
        query: str,
        *,
        kind: Optional[str] = None,
    ) -> DeviceCandidate:
        q = str(query).strip()
        if not q:
            raise DeviceSelectionError("device query cannot be empty")

        items = [c for c in candidates if kind is None or c.kind == kind]
        exact_id = [c for c in items if c.id.lower() == q.lower()]
        if len(exact_id) == 1:
            return exact_id[0]

        exact_name = [c for c in items if c.name.casefold() == q.casefold()]
        if len(exact_name) == 1:
            return exact_name[0]
        if len(exact_name) > 1:
            raise DeviceSelectionError(
                f"device name is ambiguous: {q!r}; use the device id"
            )

        partial = [
            c for c in items
            if q.casefold() in c.name.casefold() or q.casefold() in c.id.casefold()
        ]
        if len(partial) == 1:
            return partial[0]
        if not partial:
            raise DeviceSelectionError(f"device not found: {q!r}")
        raise DeviceSelectionError(
            f"device query is ambiguous: {q!r}; use the device id"
        )
