from __future__ import annotations
import re
from typing import Iterable
_SECRET=re.compile(r'(?i)(api[_-]?key|token|password|secret|authorization|cookie)\s*[:=]')
class ExperienceFeedbackGateway:
 def __init__(self,store): self.store=store
 def record_verified(self,request:str,tools:Iterable[str],evidence:dict,summary:str='',lessons=None):
  if not isinstance(evidence,dict) or evidence.get('ok') is not True:return {'recorded':False,'reason':'positive_verification_required'}
  if _SECRET.search(str(summary)):summary='[redacted]'
  item=self.store.record(request,tools,True,summary,lessons);return {'recorded':True,'signature':item['signature']}
 def record_failed(self,request:str,tools:Iterable[str],summary:str='',lessons=None):
  item=self.store.record(request,tools,False,summary,lessons);return {'recorded':True,'success':False,'signature':item['signature']}
