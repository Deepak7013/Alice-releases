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
def boot(engine,registered=True): return lambda registry,config: SimpleNamespace(registered=registered,engine=engine,reason='test')
def test_stage_receipt_has_hashes_and_does_not_store_speech_or_paths(tmp_path):
 root,cfg=setup(tmp_path); e=FakeEngine(); receipt=tmp_path/'receipt.json'
 r=run_piper_runtime_diagnostic(cfg,receipt,confirm_female=True,bootstrapper=boot(e),platform_name='Windows')
 d=json.loads(receipt.read_text()); assert r['passed'] and d['stages']['synthesis_playback']=='passed'
 assert d['stages']['configuration']=='passed' and d['stages']['provenance']=='passed' and d['stages']['engine_admission']=='passed'
 assert 'Hello' not in receipt.read_text() and str(root) not in receipt.read_text() and len(d['model_sha256'])==64
 assert d['playback_claim'].startswith('engine_return_value_only') and d['elapsed_ms'] >= 0
def test_failed_synthesis_has_stage_failure(tmp_path):
 root,cfg=setup(tmp_path); r=run_piper_runtime_diagnostic(cfg,tmp_path/'r.json',confirm_female=True,bootstrapper=boot(FakeEngine(False,'windows_playback_unavailable')),platform_name='Windows')
 assert not r['passed'] and r['stages']['synthesis_playback']=='failed' and r['error_category']=='windows_playback_unavailable'
def test_missing_config_still_writes_receipt(tmp_path):
 receipt=tmp_path/'receipt.json'; r=run_piper_runtime_diagnostic(tmp_path/'missing.json',receipt,confirm_female=True)
 assert not r['passed'] and receipt.exists() and r['stages']['configuration']=='failed'
def test_tampered_model_blocks_bootstrap(tmp_path):
 root,cfg=setup(tmp_path); (root/'female.onnx').write_bytes(b'tampered'); calls=[]
 def no_boot(*a): calls.append(1); return SimpleNamespace(registered=True,engine=FakeEngine())
 r=run_piper_runtime_diagnostic(cfg,tmp_path/'r.json',confirm_female=True,bootstrapper=no_boot,platform_name='Windows')
 assert not r['passed'] and not calls and r['stages']['provenance']=='failed'
def test_non_windows_success_not_verified(tmp_path):
 root,cfg=setup(tmp_path); r=run_piper_runtime_diagnostic(cfg,tmp_path/'r.json',confirm_female=True,bootstrapper=boot(FakeEngine()),platform_name='Linux')
 assert not r['passed'] and r['stages']['synthesis_playback']=='unverified_platform'
def test_requires_female_confirmation(tmp_path):
 root,cfg=setup(tmp_path)
 with pytest.raises(ValueError,match='female_profile_confirmation_required'): run_piper_runtime_diagnostic(cfg,tmp_path/'r.json')
def test_engine_admission_failure_is_explicit(tmp_path):
 root,cfg=setup(tmp_path); r=run_piper_runtime_diagnostic(cfg,tmp_path/'r.json',confirm_female=True,bootstrapper=boot(FakeEngine(),False),platform_name='Windows')
 assert not r['passed'] and r['stages']['engine_admission']=='failed'
def test_configured_artifact_traversal_is_blocked(tmp_path):
 root,cfg=setup(tmp_path); d=json.loads(cfg.read_text()); d['model_path']='../outside.onnx'; cfg.write_text(json.dumps(d))
 r=run_piper_runtime_diagnostic(cfg,tmp_path/'r.json',confirm_female=True,bootstrapper=boot(FakeEngine()),platform_name='Windows')
 assert not r['passed'] and r['reason']=='configuration_or_model_validation_failed'
