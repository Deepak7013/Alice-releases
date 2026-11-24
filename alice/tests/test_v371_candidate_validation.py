from alice.engineering.candidate_sandbox import CandidateSandbox
from alice.engineering.validation import CandidateValidator

def test_candidate_validation_isolated_and_verified(tmp_path):
    src=tmp_path/"src"; src.mkdir(); (src/"m.py").write_text("x=1\n",encoding="utf-8")
    sb=CandidateSandbox(src,tmp_path/"work"); root=sb.create(); sb.apply([{"path":"m.py","content":"x=2\n"}])
    r=CandidateValidator().validate(root,lambda _: (4,0))
    assert r.verified is True and r.tests_passed==4
    assert (src/"m.py").read_text(encoding="utf-8")=="x=1\n"

def test_failed_candidate_is_not_verified(tmp_path):
    src=tmp_path/"src"; src.mkdir(); root=CandidateSandbox(src,tmp_path/"work").create()
    r=CandidateValidator().validate(root,lambda _: (3,1))
    assert r.verified is False and r.tests_failed==1
