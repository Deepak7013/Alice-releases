from pathlib import Path
from alice.experience.improvement_lab import ImprovementLab

def test_successful_change_is_backed_up(tmp_path):
    p=tmp_path/"module.py"; p.write_text("VALUE=1\n")
    lab=ImprovementLab(tmp_path)
    r=lab.apply(p,"VALUE=1","VALUE=2",test=lambda: True,reason="improve")
    assert r.ok and r.changed and r.tested and p.read_text()=="VALUE=2\n"
    assert list((tmp_path/"improvement_backups").iterdir())

def test_failed_test_rolls_back(tmp_path):
    p=tmp_path/"module.py"; p.write_text("VALUE=1\n")
    lab=ImprovementLab(tmp_path)
    r=lab.apply(p,"VALUE=1","VALUE=2",test=lambda: False)
    assert not r.ok and r.rolled_back and p.read_text()=="VALUE=1\n"

def test_outside_root_rejected(tmp_path):
    lab=ImprovementLab(tmp_path/"root")
    try: lab.propose(tmp_path/"outside.py","a","b","x")
    except ValueError: pass
    else: assert False

def test_secret_file_rejected(tmp_path):
    p=tmp_path/".env"; p.write_text("X=1")
    lab=ImprovementLab(tmp_path)
    try: lab.propose(p,"X=1","X=2","x")
    except ValueError: pass
    else: assert False
