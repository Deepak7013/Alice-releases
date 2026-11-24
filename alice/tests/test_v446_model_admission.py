from alice.voice.model_admission import LocalVoiceModelAdmissionGate

def good(**overrides):
    values=dict(model_name="ALICE Local Voice",model_format="onnx",local_owned=True,offline=True,
                manifest_verified=True,license_reviewed=True,runtime_ready=True)
    values.update(overrides); return values

def test_admits_verified_reviewed_local_offline_model():
    r=LocalVoiceModelAdmissionGate().evaluate(**good())
    assert r.admitted and r.reason=="local_model_admitted"

def test_cloud_or_unowned_model_is_rejected():
    r=LocalVoiceModelAdmissionGate().evaluate(**good(local_owned=False,offline=False))
    assert not r.admitted and r.reason=="local_ownership_required"

def test_unverified_manifest_blocks_admission():
    r=LocalVoiceModelAdmissionGate().evaluate(**good(manifest_verified=False))
    assert not r.admitted and r.reason=="model_artifacts_not_verified"

def test_unreviewed_license_blocks_admission():
    r=LocalVoiceModelAdmissionGate().evaluate(**good(license_reviewed=False))
    assert not r.admitted and r.reason=="license_review_required"

def test_runtime_must_be_verified():
    r=LocalVoiceModelAdmissionGate().evaluate(**good(runtime_ready=False))
    assert not r.admitted and r.reason=="runtime_readiness_unverified"

def test_unknown_format_and_missing_name_fail_closed():
    g=LocalVoiceModelAdmissionGate()
    assert g.evaluate(**good(model_format="unknown")).reason=="model_format_unsupported"
    assert g.evaluate(**good(model_name=" ")).reason=="model_name_missing"
