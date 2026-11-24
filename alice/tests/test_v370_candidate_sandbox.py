import pytest
from alice.engineering.candidate_sandbox import CandidateSandbox

def test_candidate_changes_never_touch_source(tmp_path):
    src=tmp_path/"src"; src.mkdir(); (src/"mod.py").write_text("x=1\n",encoding="utf-8")
    sb=CandidateSandbox(src,tmp_path/"work"); sb.create(); sb.apply([{"path":"mod.py","content":"x=2\n"}])
    assert (src/"mod.py").read_text(encoding="utf-8")=="x=1\n"
    assert (sb.path/"mod.py").read_text(encoding="utf-8")=="x=2\n"

def test_candidate_blocks_escape_and_protected_paths(tmp_path):
    src=tmp_path/"src"; src.mkdir()
    sb=CandidateSandbox(src,tmp_path/"work"); sb.create()
    with pytest.raises(PermissionError): sb.apply([{"path":"../escape.py","content":"x=1"}])
    with pytest.raises(PermissionError): sb.apply([{"path":".env","content":"SECRET=x"}])
