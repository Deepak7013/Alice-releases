import hashlib
from dataclasses import replace
from alice.voice.model_admission_bridge import verify_and_admit_local_model
from alice.voice.model_receipt_chain import append_verified_receipt, verify_receipt_chain

def report(tmp_path):
 root=tmp_path/"models";root.mkdir();(root/"w.bin").write_bytes(b"voice")
 row={"name":"weights","path":"w.bin","sha256":hashlib.sha256(b"voice").hexdigest()}
 return verify_and_admit_local_model(root,[row],model_name="ALICE Voice",model_format="onnx",local_owned=True,offline=True,license_reviewed=True,runtime_ready=True)

def test_chain_appends_verified_receipt(tmp_path):
 r=report(tmp_path); chain,reason=append_verified_receipt((),r.receipt_json,r.receipt_digest)
 assert reason=="receipt_appended" and len(chain)==1 and verify_receipt_chain(chain)==(True,"receipt_chain_verified")

def test_chain_detects_modified_entry():
 from alice.voice.model_receipt_chain import ReceiptChainEntry
 digest="a"*64; entry=ReceiptChainEntry(0,"0"*64,digest,"b"*64)
 assert verify_receipt_chain((entry,))[1]=="chain_digest_mismatch"

def test_invalid_receipt_is_not_appended(tmp_path):
 chain,reason=append_verified_receipt((),"{}","0"*64)
 assert chain==() and reason.startswith("receipt_rejected:")
