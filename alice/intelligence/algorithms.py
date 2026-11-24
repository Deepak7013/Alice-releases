"""Alice's algorithm library and decision engine.

This is not a claim that one catalog contains every algorithm ever invented.
It is a curated, extensible set of high-value algorithm families Alice can
select based on objective, data shape, constraints, and verification needs.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Callable
import heapq, math, statistics
import numpy as np

@dataclass(frozen=True)
class Algorithm:
    name:str; family:str; strengths:tuple[str,...]; costs:tuple[str,...]; deterministic:bool=True

CATALOG=[
 Algorithm("tfidf_cosine","retrieval",("small_corpus","local","explainable"),("lexical_gap",)),
 Algorithm("neural_embeddings","retrieval",("semantic","paraphrase","multilingual"),("model_dependency","compute"),False),
 Algorithm("bm25","retrieval",("long_text","keyword_search","local"),("semantic_gap",)),
 Algorithm("mmr","ranking",("diversity","search_results"),("extra_scoring",)),
 Algorithm("weighted_evidence","ranking",("auditable","multi_signal"),("weight_tuning",)),
 Algorithm("kmeans","clustering",("numeric","compact_clusters"),("need_k",)),
 Algorithm("dbscan","clustering",("outliers","unknown_cluster_count"),("scale_sensitive",)),
 Algorithm("zscore","anomaly",("numeric","fast"),("distribution_assumption",)),
 Algorithm("iqr","anomaly",("numeric","robust"),("univariate",)),
 Algorithm("topological_sort","planning",("dependencies","dag"),("cycles_invalid",)),
 Algorithm("astar","planning",("pathfinding","heuristic_search"),("heuristic_needed",)),
 Algorithm("earliest_deadline_first","scheduling",("deadlines","simple"),("single_priority",)),
 Algorithm("shortest_processing_time","scheduling",("throughput","queue"),("fairness",)),
 Algorithm("greedy","optimization",("fast","monotonic_choices"),("local_optimum",)),
 Algorithm("dynamic_programming","optimization",("overlapping_subproblems","exact"),("memory",)),
 Algorithm("simulated_annealing","optimization",("large_search","nonconvex"),("stochastic","tuning"),False),
]

class AlgorithmCatalog:
    def __init__(self,algorithms=None): self.algorithms=list(algorithms or CATALOG)
    def get(self,name):
        for a in self.algorithms:
            if a.name==name:return a
        raise KeyError(name)
    def list(self): return [asdict(a) for a in self.algorithms]

class AlgorithmAdvisor:
    def __init__(self,catalog=None): self.catalog=catalog or AlgorithmCatalog()
    def recommend(self,objective,data=None,constraints=None,top_k=3):
        text=(str(objective)+" "+str(constraints or "")).lower(); data=data or {}
        scores=[]
        for a in self.catalog.algorithms:
            score=0.0; reasons=[]
            for s in a.strengths:
                if s.replace("_"," ") in text or s in text: score+=1; reasons.append(s)
            if a.family in text: score+=1.5; reasons.append("family match")
            if data.get("size") and data["size"]<1000 and "small_corpus" in a.strengths: score+=1
            if data.get("outliers") and "outliers" in a.strengths: score+=2
            if data.get("unknown_k") and "unknown_cluster_count" in a.strengths: score+=2
            if data.get("requires_exact") and "exact" in a.strengths: score+=2
            if data.get("requires_explainability") and "explainable" in a.strengths: score+=2
            if data.get("low_compute") and "compute" in a.costs: score-=1
            scores.append((score,a,reasons))
        scores.sort(key=lambda x:(x[0],x[1].deterministic),reverse=True)
        return [{"algorithm":x[1].name,"family":x[1].family,"score":round(x[0],3),"reasons":x[2],"deterministic":x[1].deterministic} for x in scores[:max(1,int(top_k))]]

class AlgorithmExecutor:
    """Small, verified implementations of common choices used by Alice."""
    @staticmethod
    def zscore(values,threshold=3.0):
        xs=[float(x) for x in values]; mean=statistics.mean(xs); sd=statistics.pstdev(xs) or 1.0
        return [i for i,x in enumerate(xs) if abs((x-mean)/sd)>threshold]
    @staticmethod
    def iqr(values,factor=1.5):
        xs=np.asarray(values,dtype=float); q1,q3=np.percentile(xs,[25,75]); i=q3-q1
        return [int(k) for k,x in enumerate(xs) if x<q1-factor*i or x>q3+factor*i]
    @staticmethod
    def topological_order(nodes,edges):
        indeg={n:0 for n in nodes}; adj={n:[] for n in nodes}
        for a,b in edges: adj[a].append(b); indeg[b]+=1
        q=[n for n in nodes if indeg[n]==0]; q.sort(); out=[]
        while q:
            n=q.pop(0); out.append(n)
            for b in adj[n]:
                indeg[b]-=1
                if indeg[b]==0:q.append(b);q.sort()
        if len(out)!=len(indeg): raise ValueError("cycle detected")
        return out
    @staticmethod
    def earliest_deadline(tasks):
        return sorted(tasks,key=lambda x:x["deadline"])
