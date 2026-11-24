"""Unified experience-learning loop for Alice.

Coordinates recall, cross-domain transfer, outcome recording, and improvement
proposals. It never executes consequential actions or expands permissions.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import json, time
from alice.experience.gateway import ExperienceGateway
from alice.experience.transfer import ExperienceTransfer
from alice.experience.semantic_retrieval import SemanticExperienceRetriever

@dataclass
class LearningDecision:
    task:str
    reusable:bool
    workflow:str|None
    confidence:float
    source:str
    alternatives:list
    reason:str

class UnifiedLearningLoop:
    def __init__(self, root=None):
        self.root=Path(root or Path.cwd())
        self.gateway=ExperienceGateway(self.root)
        self.transfer=ExperienceTransfer(self.gateway.store)
        self.semantic=SemanticExperienceRetriever(self.gateway.store)
        self.path=self.root/"alice_workspace"/"learning_loop.json"
        self.path.parent.mkdir(parents=True,exist_ok=True)

    def decide(self,task):
        direct=self.gateway.choose(task)
        if direct.selected:
            return LearningDecision(task,True,direct.selected,direct.confidence,
                                    "direct_experience",direct.alternatives,direct.reason)
        semantic=self.semantic.search(task,limit=3)
        if semantic and semantic[0]["score"] >= 0.35:
            best=semantic[0]
            return LearningDecision(task,True,best["workflow"],best["score"],
                                    "semantic_experience",
                                    [x["workflow"] for x in semantic[1:]],
                                    "semantic match with evidence")
        transferred=self.transfer.best(task)
        if transferred:
            confidence=min(.79,transferred.overlap)
            return LearningDecision(task,True,transferred.workflow,round(confidence,4),
                                    "cross_domain_transfer",[],transferred.rationale)
        return LearningDecision(task,False,None,0.0,"none",[],"no sufficiently supported experience")

    def record_outcome(self,task,workflow,success,**kwargs):
        rec=self.gateway.remember(task,workflow,success,**kwargs)
        return {"recorded":True,"success":bool(success),"task":task,"workflow":workflow,
                "timestamp":time.time()}

    def explain(self,task):
        d=self.decide(task)
        return asdict(d)
