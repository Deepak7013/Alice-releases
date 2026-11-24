from dataclasses import dataclass, field
from enum import Enum
import time
class WatchKind(str, Enum):
    DEADLINE='deadline'; CALENDAR='calendar'; CONDITION='condition'; RECURRING='recurring'
@dataclass
class Watch:
    watch_id:str; kind:str; title:str; due_at:float|None=None; interval_seconds:int|None=None; enabled:bool=True; payload:dict=field(default_factory=dict); last_run:float|None=None; created_at:float=field(default_factory=time.time)
@dataclass
class Notification:
    notification_id:str; title:str; body:str; severity:str='info'; created_at:float=field(default_factory=time.time); read:bool=False; source_id:str|None=None
