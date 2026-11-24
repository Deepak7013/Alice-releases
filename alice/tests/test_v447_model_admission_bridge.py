import hashlib
from alice.voice.model_admission_bridge import verify_and_admit_local_model

def artifact(path, data):
    return {"name":"voice-weights","path":path,"sha256":hashlib.sha256(data).hexdigest()}

def kwargs():
    return dict(model_name="ALICE Local Voice",model_format="onnx",local_owned=True,offline=True,
                license_reviewed=True,runtime_ready=True)

def test_verified_artifacts_flow_into_admission(tmp_path):
    root=tmp_path/"models"; root.mkdir(); data=b"weights"; (root/"weights.bin").write_bytes(data)
    r=verify_and_admit_local_model(root,[artifact("weights.bin",data)],**kwargs())
    assert r.admitted and r.verification.ok and r.decision.admitted
    assert r.reason=="local_model_verified_and_admitted"

def test_tampered_artifact_cannot_be_admitted(tmp_path):
    root=tmp_path/"models"; root.mkdir(); (root/"weights.bin").write_bytes(b"tampered")
    r=verify_and_admit_local_model(root,[artifact("weights.bin",b"original")],**kwargs())
    assert not r.admitted and not r.verification.ok and not r.decision.admitted
    assert r.decision.reason=="model_artifacts_not_verified"

def test_policy_still_blocks_unreviewed_license_after_hash_passes(tmp_path):
    root=tmp_path/"models"; root.mkdir(); data=b"weights"; (root/"weights.bin").write_bytes(data)
    r=verify_and_admit_local_model(root,[artifact("weights.bin",data)],**(kwargs()|{"license_reviewed":False}))
    assert r.verification.ok and not r.admitted and r.decision.reason=="license_review_required"

def test_policy_still_requires_runtime_evidence(tmp_path):
    root=tmp_path/"models"; root.mkdir(); data=b"weights"; (root/"weights.bin").write_bytes(data)
    r=verify_and_admit_local_model(root,[artifact("weights.bin",data)],**(kwargs()|{"runtime_ready":False}))
    assert r.verification.ok and not r.admitted and r.decision.reason=="runtime_readiness_unverified"

def test_missing_model_root_fails_closed(tmp_path):
    r=verify_and_admit_local_model(tmp_path/"missing",[artifact("weights.bin",b"x")],**kwargs())
    assert not r.admitted and not r.verification.ok
