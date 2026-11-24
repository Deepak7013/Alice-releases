"""License-aware integrity records for user-supplied Piper voice models.

This module records provenance and hashes; it does not determine legal status or
infer voice gender. The user must inspect the license and explicitly accept it.
"""
from __future__ import annotations
import hashlib, json, os, tempfile
from datetime import datetime, timezone
from pathlib import Path

MAX_LICENSE_BYTES = 2 * 1024 * 1024
MAX_CONFIG_BYTES = 1024 * 1024

def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def _contained(root: Path, relative: str, suffix: str | None = None) -> Path:
    raw = str(relative or '').strip()
    candidate = Path(raw)
    if not raw or candidate.is_absolute() or '\\' in raw or any(x in {'', '.', '..'} for x in candidate.parts):
        raise ValueError('unsafe_relative_artifact_path')
    resolved_root = root.resolve(strict=True)
    target = (resolved_root / candidate).resolve(strict=True)
    if not target.is_relative_to(resolved_root) or not target.is_file():
        raise ValueError('artifact_must_be_file_inside_model_root')
    if suffix and target.suffix.lower() != suffix.lower():
        raise ValueError('artifact_extension_not_supported')
    if target.stat().st_size <= 0:
        raise ValueError('artifact_is_empty')
    return target

def create_model_receipt(*, model_root: str | Path, model_path: str, config_path: str,
                         license_path: str, license_id: str, source_url: str = '',
                         confirm_female: bool = False, accept_license: bool = False,
                         receipt_path: str | Path | None = None) -> dict:
    if not confirm_female:
        raise ValueError('female_profile_confirmation_required')
    if not accept_license:
        raise ValueError('license_acceptance_required')
    license_id = str(license_id or '').strip()
    if not license_id or len(license_id) > 160:
        raise ValueError('license_identifier_required')
    source_url = str(source_url or '').strip()
    if source_url and not source_url.startswith('https://'):
        raise ValueError('source_url_must_use_https')
    root = Path(model_root).expanduser().resolve(strict=True)
    if not root.is_dir(): raise ValueError('model_root_must_be_directory')
    model = _contained(root, model_path, '.onnx')
    config = _contained(root, config_path, '.json')
    license_file = _contained(root, license_path)
    if license_file.stat().st_size > MAX_LICENSE_BYTES:
        raise ValueError('license_file_too_large')
    if config.stat().st_size > MAX_CONFIG_BYTES:
        raise ValueError('model_config_too_large')
    try: parsed=json.loads(config.read_text(encoding='utf-8'))
    except (OSError, ValueError, json.JSONDecodeError) as exc: raise ValueError('model_config_invalid_json') from exc
    if not isinstance(parsed, dict): raise ValueError('model_config_must_be_object')
    license_text=license_file.read_text(encoding='utf-8', errors='replace').strip()
    if len(license_text) < 20: raise ValueError('license_text_missing_or_too_short')
    receipt={
      'format':1,'product':'ALICE Piper model provenance','created_utc':datetime.now(timezone.utc).isoformat(),
      'model_root':str(root),'model_file':model.name,'model_sha256':sha256_file(model),'model_size_bytes':model.stat().st_size,
      'config_file':config.name,'config_sha256':sha256_file(config),'license_file':license_file.name,
      'license_sha256':sha256_file(license_file),'license_id':license_id,'license_accepted':True,
      'female_profile_user_confirmed':True,'source_url':source_url,
      'notice':'User acceptance and file hashes are recorded; ALICE does not independently certify license validity or voice gender.'}
    target=Path(receipt_path).expanduser().resolve() if receipt_path else root/'alice_model_provenance.json'
    if not target.resolve().is_relative_to(root): raise ValueError('receipt_must_be_inside_model_root')
    target.parent.mkdir(parents=True,exist_ok=True)
    temp=None
    try:
      with tempfile.NamedTemporaryFile('w',encoding='utf-8',newline='\n',dir=target.parent,prefix=target.name+'.',suffix='.tmp',delete=False) as f:
        temp=f.name; json.dump(receipt,f,indent=2,ensure_ascii=False); f.write('\n'); f.flush(); os.fsync(f.fileno())
      os.replace(temp,target); temp=None
    finally:
      if temp:
        try: Path(temp).unlink(missing_ok=True)
        except OSError: pass
    receipt['receipt_path']=str(target)
    return receipt

def audit_model_receipt(model_root: str | Path, receipt_path: str | Path | None = None) -> dict:
    root=Path(model_root).expanduser().resolve(strict=True)
    target=Path(receipt_path).expanduser().resolve() if receipt_path else root/'alice_model_provenance.json'
    if not target.is_relative_to(root): return {'ok':False,'reason':'receipt_outside_model_root'}
    try:
      if target.stat().st_size > 64*1024: return {'ok':False,'reason':'receipt_too_large'}
      data=json.loads(target.read_text(encoding='utf-8'))
    except (OSError,ValueError,json.JSONDecodeError): return {'ok':False,'reason':'receipt_missing_or_invalid'}
    if not isinstance(data,dict) or data.get('format') != 1 or not data.get('license_accepted') or not data.get('female_profile_user_confirmed'):
      return {'ok':False,'reason':'receipt_policy_fields_invalid'}
    checks={}
    for key,hashkey in [('model_file','model_sha256'),('config_file','config_sha256'),('license_file','license_sha256')]:
      try:
        file=_contained(root,str(data.get(key,'')),'.onnx' if key=='model_file' else ('.json' if key=='config_file' else None))
        checks[key]=sha256_file(file)==data.get(hashkey)
      except (OSError,ValueError): checks[key]=False
    ok=all(checks.values())
    return {'ok':ok,'reason':'model_provenance_verified' if ok else 'model_or_license_integrity_mismatch','checks':checks}
