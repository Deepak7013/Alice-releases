import hashlib, json
from alice.voice.model_admission_bridge import verify_and_admit_local_model
from alice.voice.model_receipt_chain import append_verified_receipt, create_receipt_chain_checkpoint, export_receipt_chain_checkpoint, import_receipt_chain_checkpoint

def make_checkpoint(tmp_path):
 root=tmp_path/"models";root.mkdir();(root/"w.bin").write_bytes(b"voice")
 row={"name":"weights","path":"w.bin","sha256":hashlib.sha256(b"voice").hexdigest()}
 r=verify_and_admit_local_model(root,[row],model_name="ALICE Voice",model_format="onnx",local_owned=True,offline=True,license_reviewed=True,runtime_ready=True)
 chain,_=append_verified_receipt((),r.receipt_json,r.receipt_digest)
 return create_receipt_chain_checkpoint(chain)[0]

def test_checkpoint_export_import_round_trip(tmp_path):
 cp=make_checkpoint(tmp_path); restored,reason=import_receipt_chain_checkpoint(export_receipt_chain_checkpoint(cp))
 assert restored==cp and reason=="receipt_chain_checkpoint_imported"

def test_checkpoint_import_rejects_tampered_digest(tmp_path):
 cp=make_checkpoint(tmp_path); text=export_receipt_chain_checkpoint(cp).replace(cp.head_digest,"a"*64)
 assert import_receipt_chain_checkpoint(text)[1]=="receipt_chain_checkpoint_digest_mismatch"

def test_checkpoint_import_rejects_unknown_fields():
 assert import_receipt_chain_checkpoint(json.dumps({"format":1,"entry_count":0,"head_digest":"0"*64,"checkpoint_digest":"0"*64,"x":1}))[1]=="receipt_chain_checkpoint_schema_invalid"

def test_checkpoint_import_rejects_oversized_input():
 assert import_receipt_chain_checkpoint(" "*4097)[1]=="receipt_chain_checkpoint_serialization_too_large"
