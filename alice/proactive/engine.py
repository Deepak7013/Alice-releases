from .models import Opportunity, ProactiveDecision, ProactiveAction
from .policy import ProactivePolicy

class ProactiveEngine:
    def __init__(self, policy=None):
        self.policy = policy or ProactivePolicy()

    def evaluate(self, opportunity: Opportunity):
        action = self.policy.decide(opportunity)
        if action == ProactiveAction.IGNORE:
            explanation = "Evidence or confidence is insufficient for proactive intervention."
        elif action == ProactiveAction.RESEARCH:
            explanation = "Gather more evidence before making a recommendation."
        elif action == ProactiveAction.INFORM:
            explanation = "The information is time-sensitive enough to surface proactively."
        elif action == ProactiveAction.RECOMMEND:
            explanation = "Evidence is strong enough for a useful recommendation."
        elif action == ProactiveAction.ASK:
            explanation = "The next step could have meaningful consequences, so confirmation is required."
        else:
            explanation = "Preparation is useful, but execution remains gated."
        return ProactiveDecision(action, opportunity, explanation,
                                 self.policy.requires_confirmation(action))
