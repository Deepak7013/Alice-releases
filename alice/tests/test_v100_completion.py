from alice.core.completion import AliceCompletion

def test_completion_contract():
    r=AliceCompletion.report(0)
    assert r.roadmap_version=='1.0.0'
    assert len(r.capabilities)>=9
    assert 'consequential_actions_require_explicit_approval' in r.safety_invariants
