from pathlib import Path
from alice.artifacts.factory import ArtifactFactory
from alice.artifacts.visual_qa import VisualArtifactQA

def test_reference_word_excel_visual_render(tmp_path):
    f=ArtifactFactory(tmp_path)
    w=f.create_reference_word("Report",[{"heading":"Summary","body":"Readable report content."}])
    x=f.create_reference_excel("Data",{"Data":[["Name","Value"],["A",10],["B",20]]})
    q=VisualArtifactQA()
    qw=q.inspect(w.path,"word"); qx=q.inspect(x.path,"excel")
    assert qw["ok"], qw
    assert qx["ok"], qx
