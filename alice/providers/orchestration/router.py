from dataclasses import dataclass, field
from typing import Any, Callable
@dataclass
class ModelResult:
    provider:str; model:str; output:Any; success:bool=True; error:str|None=None; metadata:dict=field(default_factory=dict)
class ModelRouter:
    def __init__(self): self._models=[]
    def register(self,provider,model,handler,capabilities=()):
        if not provider.strip() or not model.strip(): raise ValueError('provider and model are required')
        self._models.append({'provider':provider,'model':model,'handler':handler,'capabilities':set(capabilities)})
    def route(self,request,capability=None,preferred_provider=None):
        candidates=[m for m in self._models if capability is None or capability in m['capabilities']]
        if preferred_provider: candidates=sorted(candidates,key=lambda m:0 if m['provider']==preferred_provider else 1)
        if not candidates: raise LookupError('no compatible model')
        errors=[]
        for m in candidates:
            try:
                out=m['handler'](request)
                return ModelResult(m['provider'],m['model'],out,True,metadata={'capability':capability})
            except Exception as exc: errors.append(f"{m['provider']}/{m['model']}: {exc}")
        return ModelResult(candidates[0]['provider'],candidates[0]['model'],None,False,'; '.join(errors),{'capability':capability})
    def models(self): return [(m['provider'],m['model']) for m in self._models]
