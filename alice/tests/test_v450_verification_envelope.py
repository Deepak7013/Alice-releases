from alice.execution.verification_envelope import VerificationEnvelope

def test_success_requires_expected_state_observation_and_evidence():
    v = VerificationEnvelope().evaluate(action_id="a1", expected_state={"window":"ALICE"}, observed_state={"window":"ALICE"}, execution_ok=True, evidence="observed")
    assert v.verified and not v.recoverable

def test_state_mismatch_is_not_success():
    v = VerificationEnvelope().evaluate(action_id="a1", expected_state={"window":"ALICE"}, observed_state={"window":"Not ALICE"}, execution_ok=True, evidence="observed")
    assert not v.verified and v.recoverable and v.reason == "state_mismatch"

def test_missing_evidence_cannot_verify_action():
    v = VerificationEnvelope().evaluate(action_id="a1", expected_state={"ok":True}, observed_state={"ok":True}, execution_ok=True, evidence="")
    assert not v.verified and v.reason == "missing_verification_evidence"
