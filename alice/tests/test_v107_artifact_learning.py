from alice.artifacts.memory import ArtifactMemory
from alice.artifacts.agent import ArtifactAgent

def test_learning_promotes_success_and_recalls_exact(tmp_path):
    m=ArtifactMemory(tmp_path)
    m.learn_outcome("college report","word",{"style":"academic","layout":"reference"},True,{"ok":True})
    hit=m.recall_best_recipe("college report","word")
    assert hit["source"]=="exact"
    assert hit["recipe"]["style"]=="academic"

def test_learning_recalls_similar_successful_workflow(tmp_path):
    m=ArtifactMemory(tmp_path)
    m.learn_outcome("college annual report","word",{"style":"academic"},True,{"ok":True})
    hit=m.recall_best_recipe("college report","word")
    assert hit["source"]=="similar"
    assert hit["similarity"] >= .35

def test_failed_learning_is_not_selected(tmp_path):
    m=ArtifactMemory(tmp_path)
    m.learn_outcome("bad report","word",{"style":"broken"},False,{"ok":False})
    assert m.recall_best_recipe("bad report","word") is None

def test_agent_reports_recipe_provenance(tmp_path):
    a=ArtifactAgent(tmp_path)
    first=a.create("project report","word","First",[{"heading":"Intro","body":"A"}],style="academic")
    second=a.create("project report","word","Second",[{"heading":"Intro","body":"B"}])
    assert first["verification"]["ok"] and second["verification"]["ok"]
    assert second["reused_recipe"] is True
    assert second["recipe_source"]=="exact"
    assert second["recipe_similarity"]==1.0

def test_successful_workflows_are_ranked(tmp_path):
    m=ArtifactMemory(tmp_path)
    m.learn_outcome("a","word",{"style":"academic"},True)
    m.learn_outcome("b","word",{"style":"business"},True)
    rows=m.successful_workflows("word",2)
    assert len(rows)==2
    assert all(r["successes"]>0 for r in rows)
