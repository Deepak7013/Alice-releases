import subprocess, sys
from pathlib import Path
import pytest
def make_source(tmp):
 p=tmp/'source'; p.mkdir(exist_ok=True)
 (p/'female.onnx').write_bytes(b'onnx')
 (p/'female.onnx.json').write_text('{"audio":{"sample_rate":22050}}')
 (p/'LICENSE.txt').write_text('A sufficiently long license document for importer security tests.')
 return p
def base_cmd(src,dest):
 return [sys.executable,'IMPORT_PIPER_MODEL.py','--source-dir',str(src),'--model','female.onnx','--config','female.onnx.json','--license-file','LICENSE.txt','--license-id','TEST','--destination',str(dest),'--confirm-female','--accept-license']
def test_import_rejects_malformed_https_url(tmp_path):
 src=make_source(tmp_path); dest=tmp_path/'out'
 r=subprocess.run(base_cmd(src,dest)+['--source-url','https://'],capture_output=True,text=True)
 assert r.returncode==2 and not dest.exists()
def test_import_rejects_duplicate_basenames(tmp_path):
 src=make_source(tmp_path); (src/'other').mkdir(); (src/'other'/'female.onnx.json').write_text('A sufficiently long license document for importer security tests.')
 cmd=[sys.executable,'IMPORT_PIPER_MODEL.py','--source-dir',str(src),'--model','female.onnx','--config','female.onnx.json','--license-file','other/female.onnx.json','--license-id','TEST','--destination',str(tmp_path/'out'),'--confirm-female','--accept-license']
 r=subprocess.run(cmd,capture_output=True,text=True); assert r.returncode==2 and 'distinct filenames' in r.stderr
def test_import_rejects_symlink_escape(tmp_path):
 src=make_source(tmp_path); outside=tmp_path/'outside.onnx'; outside.write_bytes(b'external')
 try:
  (src/'escape.onnx').symlink_to(outside)
 except OSError as exc:
  if getattr(exc, 'winerror', None) == 1314:
   pytest.skip('Windows symlink creation privilege is unavailable')
  raise
 cmd=[sys.executable,'IMPORT_PIPER_MODEL.py','--source-dir',str(src),'--model','escape.onnx','--config','female.onnx.json','--license-file','LICENSE.txt','--license-id','TEST','--destination',str(tmp_path/'out'),'--confirm-female','--accept-license']
 r=subprocess.run(cmd,capture_output=True,text=True); assert r.returncode==2 and not (tmp_path/'out').exists()
