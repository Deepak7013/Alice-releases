
from pathlib import Path
from alice.artifacts.factory import ArtifactFactory
def test_artifact_factory_all_types(tmp_path):
    f=ArtifactFactory(tmp_path)
    w=f.create_word("Report",[{"heading":"Intro","body":"Hello"}])
    x=f.create_excel("Data",{"Sheet1":[["A","B"],[1,2]]})
    p=f.create_powerpoint("Deck",[{"title":"Title","body":"Overview"},{"title":"Next","body":"Details"}])
    pdf=f.create_pdf("Memo",[{"heading":"Summary","body":"Hello"}])
    md=f.create_text("Notes","# Notes","markdown")
    txt=f.create_text("Readme","Hello","text")
    for r in (w,x,p,pdf,md,txt):
        assert Path(r.path).exists() and r.bytes>0 and len(r.sha256)==64
