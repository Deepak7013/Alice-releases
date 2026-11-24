from alice.engineering.checkpoint import CandidateCheckpoint

def test_candidate_checkpoint_rolls_back_only_candidate(tmp_path):
    src=tmp_path/'src'; src.mkdir(); (src/'a.py').write_text('x=1\n',encoding='utf-8')
    cp=CandidateCheckpoint(src); cp.create(); (src/'a.py').write_text('x=2\n',encoding='utf-8'); cp.rollback()
    assert (src/'a.py').read_text(encoding='utf-8')=='x=1\n'
