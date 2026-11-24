from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
from typing import Any, Optional
class WorkflowStatus(str, Enum):
    DRAFT='draft'; READY='ready'; RUNNING='running'; COMPLETED='completed'; FAILED='failed'; PAUSED='paused'
@dataclass
class WorkflowStep:
    step_id:str; action:str; depends_on:list[str]=field(default_factory=list); status:str='pending'; result:Any=None; error:Optional[str]=None
@dataclass
class Workflow:
    workflow_id:str; name:str; steps:list[WorkflowStep]=field(default_factory=list); status:WorkflowStatus=WorkflowStatus.DRAFT
    created_at:str=field(default_factory=lambda:datetime.now(timezone.utc).isoformat())
