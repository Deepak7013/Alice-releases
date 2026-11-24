from dataclasses import dataclass,field
from .models import Opportunity,ProactiveAction
@dataclass
class ProactiveFinding:
 title:str; reason:str; action:ProactiveAction; evidence:list[str]=field(default_factory=list)
class ProactiveAdvisor:
 def __init__(self,engine): self.engine=engine
 def review(self,signals):
  findings=[]
  for s in signals:
   if not s.get('title') or not s.get('reason'): continue
   o=Opportunity(s['title'],s['reason'],s.get('evidence',[]),float(s.get('urgency',0)),float(s.get('confidence',.5)),float(s.get('consequence',0)))
   d=self.engine.evaluate(o)
   if d.action!=ProactiveAction.IGNORE: findings.append(ProactiveFinding(o.title,o.reason,d.action,o.evidence))
  return findings
