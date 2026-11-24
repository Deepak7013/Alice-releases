from alice.deployment.upgrade_attestation import attest

def test_attestation_binds_version_and_manifest(tmp_path):
    (tmp_path/'VERSION.txt').write_text('ALICE v3.96.0')
    (tmp_path/'full_install_manifest.json').write_text('{"version":"ALICE v3.96.0","files":[]}')
    r=attest(tmp_path,'ALICE v3.95.0')
    assert r.ok and len(r.manifest_sha256)==64

def test_attestation_rejects_missing_manifest(tmp_path):
    (tmp_path/'VERSION.txt').write_text('ALICE v3.96.0')
    assert not attest(tmp_path,'ALICE v3.95.0').ok

def test_attestation_requires_distinct_parent(tmp_path):
    (tmp_path/'VERSION.txt').write_text('ALICE v3.96.0')
    (tmp_path/'full_install_manifest.json').write_text('{}')
    assert not attest(tmp_path,'ALICE v3.96.0').ok
