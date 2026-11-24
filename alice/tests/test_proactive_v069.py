from alice.proactive import ProactiveEngine
from alice.proactive.advisor import ProactiveAdvisor
def test_advisor_surfaces_strong_signal():
 a=ProactiveAdvisor(ProactiveEngine()); out=a.review([{'title':'Deadline','reason':'due soon','confidence':.9,'urgency':.9}]); assert out
