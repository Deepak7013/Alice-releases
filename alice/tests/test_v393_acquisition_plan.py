from alice.engineering.acquisition_plan import plan_capability_acquisition

def test_local_gap_produces_inert_plan():
    p=plan_capability_acquisition('calendar integration')
    assert p.local_gap and not p.executable and 'sandbox_candidate' in p.steps

def test_external_research_is_explicit():
    p=plan_capability_acquisition('new parser',external_research_allowed=True)
    assert 'research_or_design_candidate' in p.steps and p.executable is False

def test_blank_capability_rejected():
    try: plan_capability_acquisition('')
    except ValueError: return
    assert False
