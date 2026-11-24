import json
from pathlib import Path
import subprocess, sys
from alice.voice.piper_model_provenance import audit_model_receipt

def source(tmp):
    p=tmp/'source'; p.mkdir()
    (p/'female.onnx').write_bytes(b'onnx-test')
    (p/'female.onnx.json').write_text(json.dumps({'audio':{'sample_rate':22050}}),encoding='utf-8')
    (p/'LICENSE.txt').write_text('A sufficiently long user supplied license document for the test fixture.',encoding='utf-8')
    return p

def test_import_cli_stages_and_publishes_with_receipt(tmp_path):
    src=source(tmp_path); dest=tmp_path/'managed'/'female-test'
    cmd=[sys.executable,'IMPORT_PIPER_MODEL.py','--source-dir',str(src),'--model','female.onnx','--config','female.onnx.json','--license-file','LICENSE.txt','--license-id','TEST','--source-url','https://example.invalid/model','--destination',str(dest),'--confirm-female','--accept-license']
    result=subprocess.run(cmd,capture_output=True,text=True)
    assert result.returncode==0, result.stderr
    assert audit_model_receipt(dest)['ok']
    assert (dest/'female.onnx').is_file() and (dest/'LICENSE.txt').is_file()

def test_import_cli_requires_explicit_flags(tmp_path):
    src=source(tmp_path); dest=tmp_path/'dest'
    result=subprocess.run([sys.executable,'IMPORT_PIPER_MODEL.py','--source-dir',str(src),'--model','female.onnx','--config','female.onnx.json','--license-file','LICENSE.txt','--license-id','TEST','--destination',str(dest)],capture_output=True,text=True)
    assert result.returncode==2 and not dest.exists()

def test_import_cli_refuses_existing_destination(tmp_path):
    src=source(tmp_path); dest=tmp_path/'dest'; dest.mkdir(); (dest/'keep.txt').write_text('keep')
    result=subprocess.run([sys.executable,'IMPORT_PIPER_MODEL.py','--source-dir',str(src),'--model','female.onnx','--config','female.onnx.json','--license-file','LICENSE.txt','--license-id','TEST','--destination',str(dest),'--confirm-female','--accept-license'],capture_output=True,text=True)
    assert result.returncode==3 and (dest/'keep.txt').read_text()=='keep'
