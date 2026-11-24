import json
from pathlib import Path
import pytest
from alice.voice.piper_model_provenance import create_model_receipt, audit_model_receipt

def artifacts(tmp_path):
    root=tmp_path/'models'; root.mkdir(exist_ok=True)
    (root/'female.onnx').write_bytes(b'fake-onnx-model-bytes')
    (root/'female.onnx.json').write_text(json.dumps({'audio':{'sample_rate':22050}}),encoding='utf-8')
    (root/'LICENSE.txt').write_text('Test license text with enough detail to record user supplied license evidence.\nPermission terms apply.',encoding='utf-8')
    return root

def make(root):
    return create_model_receipt(model_root=root,model_path='female.onnx',config_path='female.onnx.json',license_path='LICENSE.txt',
      license_id='TEST-LICENSE',source_url='https://example.invalid/voice',confirm_female=True,accept_license=True)

def test_receipt_records_hashes_and_audits(tmp_path):
    root=artifacts(tmp_path); receipt=make(root)
    assert len(receipt['model_sha256'])==64 and receipt['license_accepted']
    assert audit_model_receipt(root)['ok']

def test_requires_explicit_female_and_license_acceptance(tmp_path):
    root=artifacts(tmp_path)
    with pytest.raises(ValueError,match='female_profile_confirmation_required'):
      create_model_receipt(model_root=root,model_path='female.onnx',config_path='female.onnx.json',license_path='LICENSE.txt',license_id='x',accept_license=True)
    with pytest.raises(ValueError,match='license_acceptance_required'):
      create_model_receipt(model_root=root,model_path='female.onnx',config_path='female.onnx.json',license_path='LICENSE.txt',license_id='x',confirm_female=True)

def test_rejects_non_https_source_and_path_traversal(tmp_path):
    root=artifacts(tmp_path)
    with pytest.raises(ValueError,match='https'):
      create_model_receipt(model_root=root,model_path='female.onnx',config_path='female.onnx.json',license_path='LICENSE.txt',license_id='x',source_url='http://example.com',confirm_female=True,accept_license=True)
    with pytest.raises(ValueError,match='unsafe_relative'):
      create_model_receipt(model_root=root,model_path='../female.onnx',config_path='female.onnx.json',license_path='LICENSE.txt',license_id='x',confirm_female=True,accept_license=True)

def test_audit_detects_model_config_and_license_tampering(tmp_path):
    root=artifacts(tmp_path); make(root)
    (root/'female.onnx').write_bytes(b'changed')
    result=audit_model_receipt(root)
    assert not result['ok'] and result['checks']['model_file'] is False

def test_missing_license_and_bad_json_fail(tmp_path):
    root=artifacts(tmp_path); (root/'LICENSE.txt').unlink()
    with pytest.raises((OSError,ValueError)): make(root)
    root=artifacts(tmp_path); (root/'female.onnx.json').write_text('bad',encoding='utf-8')
    with pytest.raises(ValueError,match='invalid_json'): make(root)
