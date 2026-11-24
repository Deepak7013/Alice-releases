from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class ActionStatus(str, Enum):
    PLANNED = "planned"
    APPROVED = "approved"
    EXECUTED = "executed"
    VERIFIED = "verified"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class ActionRecord:
    action_id: str
    action: str
    status: ActionStatus = ActionStatus.PLANNED
    approved: bool = False
    result: Any = None
    verification: Optional[str] = None
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()
