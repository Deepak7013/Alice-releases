from alice.engineering.integrity_gate import IntegrityGate
def test_integrity_gate_blocks_bad_impact_and_regression():
 g=IntegrityGate(); assert g.evaluate({'risk':'low'},'a','a').eligible
 assert not g.evaluate({'risk':'high'},'a','a').eligible
 assert not g.evaluate({'risk':'low'},'a','b').eligible
