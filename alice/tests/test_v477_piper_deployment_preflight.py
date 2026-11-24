import json
from alice.voice.piper_model_provenance import create_model_receipt
from alice.voice.piper_deployment_preflight import run_piper_deployment_preflight
def setup(tmp):
 root=tmp/'model'; root.mkdir(exist_ok=True)
 (root/'female.onnx').write_bytes(b'onnx-test')
 (root/'female.onnx.json').write_text(json.dumps({'audio':{'sample_rate':22050}}))
 (root/'LICENSE.txt').write_text('A sufficiently long license text for preflight tests.')
 create_model_receipt(model_root=root,model_path='female.onnx',config_path='female.onnx.json',license_path='LICENSE.txt',license_id='TEST',confirm_female=True,accept_license=True)
 cfg=tmp/'runtime'/'piper_voice.json'; cfg.parent.mkdir(exist_ok=True); cfg.write_text(json.dumps({'model_root':str(root),'model_path':'female.onnx','config_path':'female.onnx.json','executable':'piper'}))
 return root,cfg
def test_preflight_does_not_execute_configured_binary(tmp_path,monkeypatch):
 root,cfg=setup(tmp_path); import subprocess
 def forbidden(*a,**k): raise AssertionError('preflight must not execute configured binary')
 monkeypatch.setattr(subprocess,'run',forbidden)
 r=run_piper_deployment_preflight(cfg,platform_name='Linux')
 assert r['execution_policy'].endswith('not run by preflight') and r['stages']['model_provenance']=='passed'
def test_missing_executable_is_reported(tmp_path):
 root,cfg=setup(tmp_path); d=json.loads(cfg.read_text()); d['executable']=str(tmp_path/'no-such-piper'); cfg.write_text(json.dumps(d))
 r=run_piper_deployment_preflight(cfg,platform_name='Windows')
 assert not r['ready_for_runtime_test'] and r['stages']['executable']=='failed'
def test_tampered_license_blocks_readiness(tmp_path):
 root,cfg=setup(tmp_path); (root/'LICENSE.txt').write_text('A different license file has replaced the source text.')
 r=run_piper_deployment_preflight(cfg,platform_name='Windows')
 assert r['stages']['model_provenance']=='failed' and not r['ready_for_runtime_test']
def test_non_windows_never_claims_windows_ready(tmp_path,monkeypatch):
 root,cfg=setup(tmp_path); import shutil
 exe=tmp_path/'fake-piper'; exe.write_text('test executable'); exe.chmod(0o755)
 monkeypatch.setattr(shutil,'which',lambda x:str(exe) if x=='piper' else None)
 r=run_piper_deployment_preflight(cfg,platform_name='Linux')
 assert not r['ready_for_runtime_test'] and r['stages']['windows_playback_host']=='not_applicable_non_windows'
def test_missing_config_returns_actionable_failure(tmp_path):
 r=run_piper_deployment_preflight(tmp_path/'missing.json',platform_name='Windows')
 assert not r['ready_for_runtime_test'] and r['stages']['configuration']=='failed'
def test_preflight_records_hashes_without_absolute_paths(tmp_path,monkeypatch):
 root,cfg=setup(tmp_path); import shutil
 exe=tmp_path/'fake-piper'; exe.write_text('test executable'); exe.chmod(0o755)
 ps=tmp_path/'powershell'; ps.write_text('test powershell'); ps.chmod(0o755)
 monkeypatch.setattr(shutil,'which',lambda x:str(exe) if x=='piper' else str(ps))
 r=run_piper_deployment_preflight(cfg,platform_name='Windows')
 assert len(r['model_sha256'])==64 and len(r['config_sha256'])==64 and r['stages']['executable']=='passed'
 assert str(root) not in json.dumps(r)
