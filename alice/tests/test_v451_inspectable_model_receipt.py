import hashlib
import json
from alice.voice.model_admission_bridge import verify_and_admit_local_model

def test_receipt_is_inspectable_and_binds_artifact_outcomes(tmp_path):
    root=tmp_path/"models"; root.mkdir(); (root/"w.bin").write_bytes(b"voice")
    row={"name":"weights","path":"w.bin","sha256":hashlib.sha256(b"voice").hexdigest()}
    report=verify_and_admit_local_model(root,[row],model_name="ALICE Voice",model_format="onnx",local_owned=True,offline=True,license_reviewed=True,runtime_ready=True)
    receipt=json.loads(report.receipt_json)
    assert report.admitted and receipt["result_admitted"] is True
    assert receipt["artifact_results"] == [{"name":"weights","ok":True,"reason":"artifact_verified"}]
    assert hashlib.sha256(report.receipt_json.encode()).hexdigest()==report.receipt_digest

def test_receipt_shows_rejected_artifact_reason(tmp_path):
    root=tmp_path/"models"; root.mkdir(); (root/"w.bin").write_bytes(b"changed")
    row={"name":"weights","path":"w.bin","sha256":hashlib.sha256(b"expected").hexdigest()}
    report=verify_and_admit_local_model(root,[row],model_name="ALICE Voice",model_format="onnx",local_owned=True,offline=True,license_reviewed=True,runtime_ready=True)
    receipt=json.loads(report.receipt_json)
    assert not report.admitted
    assert receipt["artifact_results"][0]["reason"]=="artifact_hash_mismatch"
