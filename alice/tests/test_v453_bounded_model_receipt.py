import hashlib, json
from alice.voice.model_admission_bridge import verify_model_admission_receipt

def test_receipt_verifier_rejects_oversized_input():
    text=" " * (262144+1); digest=hashlib.sha256(text.encode()).hexdigest()
    assert verify_model_admission_receipt(text,digest)[1]=="receipt_too_large"

def test_receipt_verifier_rejects_malformed_artifact_entries():
    payload={"model_name":"x","model_format":"onnx","manifest_digest":"a","verification_ok":True,"decision_admitted":True,"decision_reason":"ok","result_admitted":True,"result_reason":"ok","artifact_results":[{"name":7,"ok":True,"reason":"ok"}]}
    text=json.dumps(payload,sort_keys=True,separators=(",",":")); digest=hashlib.sha256(text.encode()).hexdigest()
    assert verify_model_admission_receipt(text,digest)[1]=="receipt_artifact_entry_invalid"

def test_receipt_verifier_rejects_too_many_artifact_entries():
    payload={"model_name":"x","model_format":"onnx","manifest_digest":"a","verification_ok":True,"decision_admitted":True,"decision_reason":"ok","result_admitted":True,"result_reason":"ok","artifact_results":[{"name":"a","ok":True,"reason":"ok"}]*513}
    text=json.dumps(payload,sort_keys=True,separators=(",",":")); digest=hashlib.sha256(text.encode()).hexdigest()
    assert verify_model_admission_receipt(text,digest)[1]=="receipt_artifact_results_invalid"
