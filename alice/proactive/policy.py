from .models import ProactiveAction

class ProactivePolicy:
    consequential = {ProactiveAction.PREPARE}

    def decide(self, opportunity):
        if opportunity.confidence < 0.6:
            return ProactiveAction.IGNORE
        if opportunity.consequence >= 0.7:
            return ProactiveAction.ASK
        if opportunity.urgency >= 0.8:
            return ProactiveAction.INFORM
        if opportunity.confidence >= 0.8:
            return ProactiveAction.RECOMMEND
        return ProactiveAction.RESEARCH

    def requires_confirmation(self, action):
        return action in {ProactiveAction.ASK, ProactiveAction.PREPARE}
