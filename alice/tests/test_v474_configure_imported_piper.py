import json, subprocess, sys
from pathlib import Path
def model_dir(tmp):
 root=tmp/'model'; root.mkdir(exist_ok=True)
 (root/'female.onnx').write_bytes(b'model-data')
 (root/'female.onnx.json').write_text(json.dumps({'audio':{'sample_rate':22050}}))
 (root/'LICENSE.txt').write_text('A sufficiently long license document for configuration integration tests.')
 from alice.voice.piper_model_provenance import create_model_receipt
 create_model_receipt(model_root=root,model_path='female.onnx',config_path='female.onnx.json',license_path='LICENSE.txt',license_id='TEST',confirm_female=True,accept_license=True)
 return root
def run(root,model,exe,extra=()):
 return subprocess.run([sys.executable,'CONFIGURE_IMPORTED_PIPER.py','--model-dir',str(model),'--alice-root',str(root),'--executable',str(exe),'--confirm-female','--accept-license',*extra],capture_output=True,text=True)
def test_configure_uses_audited_model_and_production_admission(tmp_path):
 root=tmp_path/'alice'; root.mkdir(); model=model_dir(tmp_path); exe=tmp_path/'piper.exe'; exe.write_bytes(b'fake executable')
 r=run(root,model,exe); assert r.returncode==0,r.stderr
 cfg=json.loads((root/'alice_workspace/runtime/piper_voice.json').read_text()); assert cfg['gender']=='female' and cfg['model_path']=='female.onnx'
def test_configure_refuses_tampered_model_receipt(tmp_path):
 root=tmp_path/'alice'; root.mkdir(); model=model_dir(tmp_path); exe=tmp_path/'piper.exe'; exe.write_bytes(b'fake executable')
 (model/'female.onnx').write_bytes(b'tampered')
 r=run(root,model,exe); assert r.returncode==3 and not (root/'alice_workspace/runtime/piper_voice.json').exists()
def test_configure_requires_explicit_confirmations(tmp_path):
 root=tmp_path/'alice'; root.mkdir(); model=model_dir(tmp_path); exe=tmp_path/'piper.exe'; exe.write_bytes(b'fake executable')
 r=subprocess.run([sys.executable,'CONFIGURE_IMPORTED_PIPER.py','--model-dir',str(model),'--alice-root',str(root),'--executable',str(exe)],capture_output=True,text=True)
 assert r.returncode==2 and not (root/'alice_workspace/runtime/piper_voice.json').exists()
def test_configure_does_not_overwrite_existing_config_by_default(tmp_path):
 root=tmp_path/'alice'; root.mkdir(); model=model_dir(tmp_path); exe=tmp_path/'piper.exe'; exe.write_bytes(b'fake executable')
 assert run(root,model,exe).returncode==0
 cfg=root/'alice_workspace/runtime/piper_voice.json'; before=cfg.read_bytes()
 r=run(root,model,exe); assert r.returncode==4 and cfg.read_bytes()==before
