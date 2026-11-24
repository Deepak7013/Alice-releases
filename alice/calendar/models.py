from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class CalendarEvent:
    event_id: str
    title: str
    start: str
    end: str
    description: str = ""
    location: str = ""
    recurrence: Optional[str] = None
    reminders: list[int] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0
    cancelled: bool = False
