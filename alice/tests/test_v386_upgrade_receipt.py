from alice.deployment.upgrade_receipt import create_receipt

def test_receipt_binds_evidence():
 r=create_receipt('3.86.0','candidate',['a.py'],{'ok':True})
 assert r.ready and not r.executed and len(r.evidence_digest)==64

def test_receipt_changes_when_evidence_changes():
 a=create_receipt('3.86.0','candidate',['a.py'],{'ok':True})
 b=create_receipt('3.86.0','candidate',['a.py'],{'ok':False})
 assert a.evidence_digest != b.evidence_digest

def test_receipt_empty_files_not_ready():
 assert not create_receipt('3.86.0','candidate',[],{'ok':True}).ready
