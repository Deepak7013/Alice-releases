from dataclasses import dataclass, field
from typing import Any
@dataclass
class IntegrationStatus:
    name:str; available:bool=False; authenticated:bool=False; capabilities:list[str]=field(default_factory=list); detail:str=''
class IntegrationRegistry:
    def __init__(self): self._items={}
    def register(self,status): self._items[status.name]=status
    def get(self,name): return self._items.get(name)
    def list(self): return list(self._items.values())
