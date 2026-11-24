import hashlib, json
from alice.voice.model_admission_bridge import verify_and_admit_local_model
from alice.voice.model_receipt_chain import append_verified_receipt, export_receipt_chain, import_receipt_chain

def make_chain(tmp_path):
 root=tmp_path/"models";root.mkdir();(root/"w.bin").write_bytes(b"voice")
 row={"name":"weights","path":"w.bin","sha256":hashlib.sha256(b"voice").hexdigest()}
 r=verify_and_admit_local_model(root,[row],model_name="ALICE Voice",model_format="onnx",local_owned=True,offline=True,license_reviewed=True,runtime_ready=True)
 return append_verified_receipt((),r.receipt_json,r.receipt_digest)[0]

def test_chain_export_import_round_trip(tmp_path):
 chain=make_chain(tmp_path); text=export_receipt_chain(chain); restored,reason=import_receipt_chain(text)
 assert reason=="receipt_chain_imported" and restored==chain

def test_import_rejects_tampered_chain():
 payload={"format":1,"entries":[{"index":0,"previous_digest":"0"*64,"receipt_digest":"a"*64,"chain_digest":"b"*64}]}
 restored,reason=import_receipt_chain(json.dumps(payload))
 assert restored==() and reason.startswith("receipt_chain_rejected:")

def test_import_rejects_oversized_serialization():
 restored,reason=import_receipt_chain(" "*(262144+1))
 assert restored==() and reason=="receipt_chain_serialization_too_large"

def test_import_rejects_unknown_fields():
 restored,reason=import_receipt_chain(json.dumps({"format":1,"entries":[],"unexpected":True}))
 assert restored==() and reason=="receipt_chain_schema_invalid"
