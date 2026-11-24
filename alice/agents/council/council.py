from collections import Counter
from .models import SpecialistResult, CouncilDecision
class AgentCouncil:
    def __init__(self, specialists=None): self.specialists=dict(specialists or {})
    def register(self,name,handler):
        if not name.strip(): raise ValueError('specialist name is required')
        self.specialists[name]=handler
    def consult(self,question,names=None):
        chosen=names or list(self.specialists)
        if not chosen: raise ValueError('no specialists available')
        results=[]
        for name in chosen:
            if name not in self.specialists: raise KeyError(name)
            value=self.specialists[name](question)
            if not isinstance(value,SpecialistResult): raise TypeError('specialist must return SpecialistResult')
            results.append(value)
        # Deterministic consensus: highest aggregate confidence among exact answers.
        groups={}
        for r in results: groups.setdefault(repr(r.answer),[]).append(r)
        winner=max(groups.values(), key=lambda rs:(sum(r.confidence for r in rs),len(rs)))
        confidence=min(1.0,sum(r.confidence for r in winner)/max(1,len(winner)))
        disagreements=[r.specialist for r in results if r not in winner]
        return CouncilDecision(winner[0].answer,confidence,[r.specialist for r in winner],disagreements)
