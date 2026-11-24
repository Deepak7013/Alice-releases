import hashlib, json
from alice.voice.model_admission_bridge import verify_and_admit_local_model, verify_model_admission_receipt

def make_report(tmp_path):
    root=tmp_path/"models"; root.mkdir(); (root/"w.bin").write_bytes(b"voice")
    row={"name":"weights","path":"w.bin","sha256":hashlib.sha256(b"voice").hexdigest()}
    return verify_and_admit_local_model(root,[row],model_name="ALICE Voice",model_format="onnx",local_owned=True,offline=True,license_reviewed=True,runtime_ready=True)

def test_receipt_verifier_accepts_intact_receipt(tmp_path):
    r=make_report(tmp_path)
    assert verify_model_admission_receipt(r.receipt_json,r.receipt_digest,expected_admitted=True)==(True,"receipt_verified")

def test_receipt_verifier_rejects_tampering(tmp_path):
    r=make_report(tmp_path)
    altered=r.receipt_json.replace("ALICE Voice","Other Voice")
    assert verify_model_admission_receipt(altered,r.receipt_digest)[1]=="receipt_digest_mismatch"

def test_receipt_verifier_rejects_inconsistent_outcome():
    payload={"model_name":"x","model_format":"onnx","manifest_digest":"a","verification_ok":False,"decision_admitted":True,"decision_reason":"ok","result_admitted":True,"result_reason":"bad","artifact_results":[]}
    text=json.dumps(payload,sort_keys=True,separators=(",",":")); digest=hashlib.sha256(text.encode()).hexdigest()
    assert verify_model_admission_receipt(text,digest)[1]=="receipt_outcome_inconsistent"
