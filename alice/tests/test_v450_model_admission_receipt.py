import hashlib
from alice.voice.model_admission_bridge import verify_and_admit_local_model


def artifact(path, data=b"weights"):
    return {"name": "voice-weights", "path": path, "sha256": hashlib.sha256(data).hexdigest()}


def kwargs(**overrides):
    values = dict(model_name="ALICE Local Voice", model_format="onnx", local_owned=True,
                  offline=True, license_reviewed=True, runtime_ready=True)
    values.update(overrides)
    return values


def test_admission_receipt_digest_is_present_and_stable(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    (root / "weights.bin").write_bytes(b"weights")
    a = verify_and_admit_local_model(root, [artifact("weights.bin")], **kwargs())
    b = verify_and_admit_local_model(root, [artifact("weights.bin")], **kwargs())
    assert a.admitted and a.receipt_digest
    assert a.receipt_digest == b.receipt_digest
    assert len(a.receipt_digest) == 64


def test_receipt_digest_changes_when_policy_decision_changes(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    (root / "weights.bin").write_bytes(b"weights")
    art = [artifact("weights.bin")]
    accepted = verify_and_admit_local_model(root, art, **kwargs())
    denied = verify_and_admit_local_model(root, art, **kwargs(license_reviewed=False))
    assert accepted.receipt_digest != denied.receipt_digest
    assert accepted.admitted and not denied.admitted


def test_receipt_does_not_turn_rejected_model_into_admission(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    (root / "weights.bin").write_bytes(b"tampered")
    result = verify_and_admit_local_model(root, [artifact("weights.bin")], **kwargs())
    assert not result.admitted
    assert result.receipt_digest
