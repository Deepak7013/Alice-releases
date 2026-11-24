
from pathlib import Path
from alice.experience.global_store import GlobalExperienceStore

def test_global_experience_persists(tmp_path):
    s=GlobalExperienceStore(tmp_path)
    s.record("create college presentation","research_outline_create_verify",True,tools=["research","ppt"])
    r=GlobalExperienceStore(tmp_path).recall("make a college presentation",limit=1)
    assert r and r[0]["experience"]["success"] is True

def test_failed_experience_excluded_by_default(tmp_path):
    s=GlobalExperienceStore(tmp_path)
    s.record("delete everything","unsafe_workflow",False)
    assert s.recall("delete everything")==[]

def test_secrets_are_redacted(tmp_path):
    s=GlobalExperienceStore(tmp_path)
    s.record("task","wf",True,evidence={"token":"secret123","api_key":"abc"})
    raw=(Path(tmp_path)/"alice_workspace/global_experience.json").read_text()
    assert "secret123" not in raw and "abc" not in raw

def test_bounded_memory(tmp_path):
    s=GlobalExperienceStore(tmp_path,max_records=3)
    for i in range(6): s.record(f"task {i}","wf",True)
    assert len(s.records)==3
    assert s.stats()["records"]==3


def test_nested_secrets_are_redacted(tmp_path):
    s=GlobalExperienceStore(tmp_path)
    s.record("task","wf",True,evidence={"meta":{"authorization":"Bearer TOPSECRET","nested":{"password":"pw"}}})
    raw=(Path(tmp_path)/"alice_workspace/global_experience.json").read_text()
    assert "TOPSECRET" not in raw and '"password": "pw"' not in raw
