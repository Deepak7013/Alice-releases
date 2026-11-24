from alice.learning.regression_seed import RegressionSeedGenerator

def test_verified_failure_creates_deterministic_seed():
    g=RegressionSeedGenerator(); a=g.create(scenario='state mismatch',expected='must not claim success',reason='verification',verified_failure=True); b=g.create(scenario='state mismatch',expected='must not claim success',reason='verification',verified_failure=True)
    assert a['created'] and a['seed']['fingerprint']==b['seed']['fingerprint']

def test_unverified_failure_cannot_create_seed():
    r=RegressionSeedGenerator().create(scenario='x',expected='y',reason='z',verified_failure=False)
    assert not r['created'] and r['reason']=='verified_failure_required'

def test_incomplete_case_is_rejected():
    r=RegressionSeedGenerator().create(scenario='',expected='y',reason='z',verified_failure=True)
    assert not r['created'] and r['reason']=='scenario_and_expected_required'
