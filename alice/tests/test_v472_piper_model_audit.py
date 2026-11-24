import json
from alice.voice.piper_model_provenance import create_model_receipt, audit_model_receipt
def setup(root):
 root.mkdir(exist_ok=True)
 (root/'female.onnx').write_bytes(b'onnx test data')
 (root/'female.onnx.json').write_text(json.dumps({'audio':{'sample_rate':22050}}),encoding='utf-8')
 (root/'LICENSE.txt').write_text('A sufficiently long license file for testing integrity audit.',encoding='utf-8')
 create_model_receipt(model_root=root,model_path='female.onnx',config_path='female.onnx.json',license_path='LICENSE.txt',license_id='TEST',confirm_female=True,accept_license=True)
def test_audit_rejects_receipt_outside_root(tmp_path):
 root=tmp_path/'models'; setup(root); outside=tmp_path/'outside.json'; outside.write_text('{}')
 assert audit_model_receipt(root,outside)['reason']=='receipt_outside_model_root'
def test_audit_rejects_receipt_tampering(tmp_path):
 root=tmp_path/'models'; setup(root); receipt=root/'alice_model_provenance.json'; data=json.loads(receipt.read_text()); data['license_accepted']=False; receipt.write_text(json.dumps(data))
 assert audit_model_receipt(root)['reason']=='receipt_policy_fields_invalid'
def test_audit_detects_license_and_config_changes(tmp_path):
 root=tmp_path/'models'; setup(root); (root/'LICENSE.txt').write_text('Different license terms changed after import.')
 result=audit_model_receipt(root); assert not result['ok'] and result['checks']['license_file'] is False
 (root/'LICENSE.txt').write_text('A sufficiently long license file for testing integrity audit.')
 (root/'female.onnx.json').write_text('{}'); result=audit_model_receipt(root)
 assert not result['ok'] and result['checks']['config_file'] is False
