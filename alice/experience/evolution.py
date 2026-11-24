"""Turns repeated experience into conservative recommendations, not unchecked self-modification."""
from collections import Counter

class ExperienceEvolution:
    def __init__(self, store):
        self.store=store
    def recommend(self, request):
        matches=self.store.recall(request, limit=10)
        if not matches: return {"reusable":False,"reason":"No prior workflow"}
        successful=[m for m in matches if m.get("success")]
        if not successful: return {"reusable":False,"reason":"No successful prior workflow"}
        counts=Counter(t for m in successful for t in m.get("tools",[]))
        return {"reusable":True,"tools":[t for t,_ in counts.most_common(12)],"examples":len(successful)}
