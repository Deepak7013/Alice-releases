import hashlib
from alice.voice.model_admission_bridge import verify_and_admit_local_model
from alice.voice.model_receipt_chain import append_verified_receipt, create_receipt_chain_checkpoint, verify_receipt_chain_checkpoint

def chain(tmp_path):
 root=tmp_path/"models";root.mkdir();(root/"w.bin").write_bytes(b"voice")
 row={"name":"weights","path":"w.bin","sha256":hashlib.sha256(b"voice").hexdigest()}
 r=verify_and_admit_local_model(root,[row],model_name="ALICE Voice",model_format="onnx",local_owned=True,offline=True,license_reviewed=True,runtime_ready=True)
 return append_verified_receipt((),r.receipt_json,r.receipt_digest)[0]

def test_checkpoint_verifies_full_chain(tmp_path):
 c=chain(tmp_path); cp,reason=create_receipt_chain_checkpoint(c)
 assert reason=="receipt_chain_checkpoint_created" and verify_receipt_chain_checkpoint(c,cp)==(True,"receipt_chain_checkpoint_verified")

def test_checkpoint_detects_truncated_chain(tmp_path):
 c=chain(tmp_path); cp,_=create_receipt_chain_checkpoint(c)
 assert verify_receipt_chain_checkpoint((),cp)[1]=="receipt_chain_checkpoint_length_mismatch"

def test_checkpoint_detects_modified_seal(tmp_path):
 c=chain(tmp_path); cp,_=create_receipt_chain_checkpoint(c)
 from dataclasses import replace
 assert verify_receipt_chain_checkpoint(c,replace(cp,checkpoint_digest="0"*64))[1]=="receipt_chain_checkpoint_digest_mismatch"
