import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from alice.voice.piper_model_provenance import create_model_receipt
from alice.voice.piper_runtime_diagnostic import run_piper_runtime_diagnostic
class FakeEngine:
 def __init__(self,ok=True,error=''): self.ok=ok; self.last_error=error; self.spoken=[]
 def speak(self,text): self.spoken.append(text); return self.ok
def setup(tmp):
 root=tmp/'model'; root.mkdir(exist_ok=True)
 (root/'female.onnx').write_bytes(b'onnx-test')
 (root/'female.onnx.json').write_text(json.dumps({'audio':{'sample_rate':22050}}))
 (root/'LICENSE.txt').write_text('A sufficiently long license text for runtime diagnostic tests.')
 create_model_receipt(model_root=root,model_path='female.onnx',config_path='female.onnx.json',license_path='LICENSE.txt',license_id='TEST',confirm_female=True,accept_license=True)
 cfg=tmp/'runtime'/'piper_voice.json'; cfg.parent.mkdir(exist_ok=True); cfg.write_text(json.dumps({'model_root':str(root),'model_path':'female.onnx','config_path':'female.onnx.json','executable':'piper'}))
 return root,cfg
def boot(engine,registered=True):
 return lambda registry,config: SimpleNamespace(registered=registered,engine=engine,reason='test')
def test_diagnostic_records_success_and_no_spoken_text(tmp_path):
 root,cfg=setup(tmp_path); e=FakeEngine(); receipt=tmp_path/'receipt.json'
 r=run_piper_runtime_diagnostic(cfg,receipt,confirm_female=True,bootstrapper=boot(e),platform_name='Windows')
 data=json.loads(receipt.read_text()); assert r['passed'] and data['reason']=='piper_synthesis_and_playback_passed'
 assert 'Hello' not in receipt.read_text() and len(data['model_sha256'])==64 and e.spoken
def test_diagnostic_does_not_count_engine_failure_as_success(tmp_path):
 root,cfg=setup(tmp_path); receipt=tmp_path/'receipt.json'
 r=run_piper_runtime_diagnostic(cfg,receipt,confirm_female=True,bootstrapper=boot(FakeEngine(False,'windows_playback_unavailable')),platform_name='Windows')
 assert not r['passed'] and r['error_category']=='windows_playback_unavailable'
def test_diagnostic_requires_female_confirmation(tmp_path):
 root,cfg=setup(tmp_path)
 with pytest.raises(ValueError,match='female_profile_confirmation_required'):
  run_piper_runtime_diagnostic(cfg,tmp_path/'receipt.json')
def test_diagnostic_blocks_tampered_model_before_bootstrap(tmp_path):
 root,cfg=setup(tmp_path); (root/'female.onnx').write_bytes(b'tampered'); called=[]
 def no_boot(*a): called.append(True); return SimpleNamespace(registered=True,engine=FakeEngine())
 r=run_piper_runtime_diagnostic(cfg,tmp_path/'receipt.json',confirm_female=True,bootstrapper=no_boot,platform_name='Windows')
 assert not r['passed'] and r['reason']=='model_provenance_audit_failed' and not called
def test_non_windows_success_is_not_reported_as_playback_verified(tmp_path):
 root,cfg=setup(tmp_path); r=run_piper_runtime_diagnostic(cfg,tmp_path/'receipt.json',confirm_female=True,bootstrapper=boot(FakeEngine()),platform_name='Linux')
 assert not r['passed'] and r['reason']=='engine_reported_success_non_windows_playback_unverified'
