from dataclasses import dataclass,field
from typing import Callable,Any
@dataclass
class ResearchSource:
 locator:str; title:str=''; content:str=''; trust:float=.5
@dataclass
class ResearchReport:
 question:str; sources:list[ResearchSource]=field(default_factory=list); findings:list[str]=field(default_factory=list); contradictions:list[str]=field(default_factory=list); uncertainty:list[str]=field(default_factory=list); conclusion:str=''
class ResearchPipeline:
 def __init__(self,fetcher:Callable[[str],ResearchSource]|None=None): self.fetcher=fetcher
 def run(self,question,locators):
  if not question.strip(): raise ValueError('question is required')
  if self.fetcher is None and locators: raise RuntimeError('research fetcher is not configured')
  sources=[]
  for loc in locators:
   src=self.fetcher(loc); sources.append(src)
  findings=[]
  for s in sources:
   if s.content.strip(): findings.append(f'{s.title or s.locator}: {s.content.strip()[:500]}')
  return ResearchReport(question,sources,findings,[],['Independent verification may be required.'] if sources else ['No sources were collected.'], '')
