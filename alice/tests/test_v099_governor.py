from pathlib import Path
from alice.evolution.governor import EvolutionGovernor

def test_change_review_creates_backup(tmp_path):
    p=tmp_path/'alice'/'x.py'; p.parent.mkdir(parents=True); p.write_text('x=1')
    r=EvolutionGovernor().review('alice/x.py',tmp_path)
    assert r.allowed and Path(r.backup).exists() and r.digest_before

def test_protected_path_rejected(tmp_path):
    p=tmp_path/'alice'/'security'/'x.py'; p.parent.mkdir(parents=True); p.write_text('x=1')
    assert not EvolutionGovernor().review('alice/security/x.py',tmp_path).allowed
