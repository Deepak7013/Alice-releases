
from alice.experience.gateway import ExperienceGateway

def test_gateway_unifies_record_recall_and_choice(tmp_path):
    g=ExperienceGateway(tmp_path)
    g.remember("create annual report","research_write_verify",True,
               evidence={"verified":True,"quality":1},tools=["research","docx"])
    assert g.recommend("create annual report")
    assert g.choose("create annual report").selected=="research_write_verify"

def test_gateway_preserves_failed_experience_as_non_reusable(tmp_path):
    g=ExperienceGateway(tmp_path)
    g.remember("send payment","payment_workflow",False)
    assert g.choose("send payment").selected is None
