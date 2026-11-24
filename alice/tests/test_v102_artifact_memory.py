
from alice.artifacts.memory import ArtifactMemory
def test_artifact_memory_persists_and_recalls(tmp_path):
    m=ArtifactMemory(tmp_path)
    m.remember_style("word",{"font":"Aptos","heading":"bold"})
    m.remember_recipe("college report","word",{"sections":6,"layout":"formal"})
    assert m.get_style("word")["font"]=="Aptos"
    assert m.recall_recipe("college report","word")["sections"]==6
    assert ArtifactMemory(tmp_path).get_style("word")["heading"]=="bold"
def test_artifact_memory_redacts_secrets(tmp_path):
    m=ArtifactMemory(tmp_path); m.remember_style("word",{"note":"token=SECRET123"})
    assert "SECRET123" not in m.get_style("word")["note"]
