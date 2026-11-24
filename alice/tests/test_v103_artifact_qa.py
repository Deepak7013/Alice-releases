
from pathlib import Path
from alice.artifacts.factory import ArtifactFactory
from alice.artifacts.qa import ArtifactQA
def test_artifact_qa_validates_native_files(tmp_path):
    f=ArtifactFactory(tmp_path); q=ArtifactQA()
    results=[
      f.create_word("W",[{"body":"x"}]), f.create_excel("X",{"S":[["a"],[1]]}),
      f.create_powerpoint("P",[{"title":"T","body":"x"}]), f.create_pdf("D",[{"body":"x"}])
    ]
    assert q.inspect_many([r.path for r in results])["ok"]
def test_artifact_qa_rejects_fake_docx(tmp_path):
    p=Path(tmp_path)/"bad.docx"; p.write_text("not office")
    assert not ArtifactQA().inspect(p,"word")["ok"]
