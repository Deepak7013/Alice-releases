
from alice.artifacts.factory import ArtifactFactory
from alice.artifacts.styles import resolve_style
from alice.artifacts.qa import ArtifactQA
def test_alice_style_profiles(tmp_path):
    assert resolve_style("business").title_size==30
    f=ArtifactFactory(tmp_path)
    w=f.create_styled_word("Styled",[{"heading":"Section","body":"Text"}],"academic")
    x=f.create_styled_excel("StyledData",{"Data":[["A","B"],[1,2]]},"business")
    assert ArtifactQA().inspect(w.path)["ok"] and ArtifactQA().inspect(x.path)["ok"]
