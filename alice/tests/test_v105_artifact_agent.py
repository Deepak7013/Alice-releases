
from alice.artifacts.agent import ArtifactAgent
def test_artifact_agent_reuses_recipe(tmp_path):
    a=ArtifactAgent(tmp_path)
    first=a.create("college report","word","Report",[{"heading":"Intro","body":"A"}],style="academic")
    second=a.create("college report","word","Report2",[{"heading":"Intro","body":"B"}])
    assert first["verification"]["ok"] and second["verification"]["ok"]
    assert second["reused_recipe"] is True
def test_artifact_agent_aliases(tmp_path):
    a=ArtifactAgent(tmp_path)
    r=a.create("sales deck","slides","Deck",[{"title":"Start","body":"One"}],remember=False)
    assert r["artifact"].kind=="powerpoint"
