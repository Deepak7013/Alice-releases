from dataclasses import dataclass,field
import time
@dataclass
class ProjectTask:
 task_id:str; title:str; status:str='todo'; priority:str='normal'; due_at:float|None=None; dependencies:list[str]=field(default_factory=list); project_id:str=''
@dataclass
class Project:
 project_id:str; name:str; description:str=''; status:str='active'; tags:list[str]=field(default_factory=list); created_at:float=field(default_factory=time.time); updated_at:float=field(default_factory=time.time)
