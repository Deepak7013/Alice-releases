"""Persistent, provenance-aware knowledge and research memory for Alice."""
from .models import KnowledgeItem, SourceEvidence, ResearchSession, Claim
from .store import KnowledgeStore
from .retriever import KnowledgeRetriever
from .research import ResearchEngine

__all__ = [
    "KnowledgeItem", "SourceEvidence", "ResearchSession", "Claim",
    "KnowledgeStore", "KnowledgeRetriever", "ResearchEngine",
]
