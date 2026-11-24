from typing import Iterable
from .engine import ProactiveEngine
from ..memory_context.retriever import ContextRetriever

class ProactiveContextBridge:
    def __init__(self, memory, engine=None):
        self.memory = memory
        self.retriever = ContextRetriever(memory)
        self.engine = engine or ProactiveEngine()

    def evaluate(self, title, reason, query, urgency=0.0, confidence=0.5, consequence=0.0):
        context = self.retriever.context(query)
        evidence = [m.content for m in context]
        from .models import Opportunity
        return self.engine.evaluate(Opportunity(
            title, reason, evidence, urgency, confidence, consequence))
