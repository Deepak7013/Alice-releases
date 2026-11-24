from dataclasses import dataclass,field
@dataclass
class AgentBrief:
 goal:str; projects:list=dict; calendar:list=dict; notifications:list=dict; research:list=dict; suggestions:list=dict; actions:list=dict
class UnifiedPersonalAgent:
 def __init__(self,project_store=None,calendar_store=None,monitoring_store=None,knowledge_graph=None,proactive_advisor=None,research_pipeline=None,email_service=None,action_engine=None):
  self.projects=project_store; self.calendar=calendar_store; self.monitoring=monitoring_store; self.graph=knowledge_graph; self.proactive=proactive_advisor; self.research=research_pipeline; self.email=email_service; self.action_engine=action_engine
 def brief(self,goal=''):
  return AgentBrief(goal, self.projects.tasks() if self.projects else [], self.calendar.list() if self.calendar else [], self.monitoring.notifications(True) if self.monitoring else [], [], [], [])
 def prepare(self,goal,signals=None):
  b=self.brief(goal)
  if self.proactive and signals: b.suggestions=self.proactive.review(signals)
  return b
 def requires_confirmation(self,action):
  return action in {'send_email','delete','purchase','publish','install','transfer_money','execute_external'}
 def execute_approved(self,action,approved=False):
  if self.requires_confirmation(action) and not approved: raise PermissionError('explicit approval required')
  if self.action_engine:
   record=self.action_engine.plan(action)
   if self.requires_confirmation(action): self.action_engine.approve(record.action_id)
   return {'ok':True,'action':action,'action_id':record.action_id,'status':record.status.value}
  return {'ok':True,'action':action}
