from alice.experience.global_store import GlobalExperienceStore
from alice.experience.transfer import ExperienceTransfer

def test_transfer_between_related_domains(tmp_path):
    s=GlobalExperienceStore(tmp_path)
    s.record("create academic report", "structured_outline", True)
    x=ExperienceTransfer(s).best("create academic presentation")
    assert x and x.workflow=="structured_outline"

def test_unrelated_domain_not_transferred(tmp_path):
    s=GlobalExperienceStore(tmp_path)
    s.record("cook pasta", "recipe", True)
    assert ExperienceTransfer(s).best("compile android software") is None

def test_failed_experience_not_transferred(tmp_path):
    s=GlobalExperienceStore(tmp_path)
    s.record("create report", "bad_workflow", False)
    assert ExperienceTransfer(s).best("create presentation") is None

def test_transfer_explains_shared_capabilities(tmp_path):
    s=GlobalExperienceStore(tmp_path)
    s.record("research university project", "research_workflow", True)
    x=ExperienceTransfer(s).best("investigate academic project")
    assert x and "shared capabilities" in x.rationale
