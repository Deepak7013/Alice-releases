from alice.evolution.evidence import EvidenceBinder
def test_evidence_binding_is_deterministic():
 b=EvidenceBinder().bind('p1',{'ok':True,'tests':10}); assert EvidenceBinder().matches(b,{'tests':10,'ok':True})
 assert not EvidenceBinder().matches(b,{'ok':False,'tests':10})
