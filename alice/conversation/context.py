from dataclasses import dataclass, field
from typing import Any
@dataclass
class ConversationContext:
    turns:list[dict[str,Any]]=field(default_factory=list)
    variables:dict[str,Any]=field(default_factory=dict)
    def add(self,role,content,**meta): self.turns.append({'role':role,'content':content,**meta})
    def recent(self,n=10): return self.turns[-max(0,int(n)):]
    def set(self,key,value): self.variables[key]=value
    def get(self,key,default=None): return self.variables.get(key,default)
