from alice.experience.store import ExperienceStore
from alice.experience.feedback_gateway import ExperienceFeedbackGateway
def test_success_requires_positive_evidence(tmp_path):
 s=ExperienceStore(tmp_path);g=ExperienceFeedbackGateway(s)
 assert not g.record_verified('x',['tool'],{'ok':False})['recorded'];assert g.record_verified('x',['tool'],{'ok':True})['recorded']
def test_failed_feedback_is_recorded(tmp_path):
 s=ExperienceStore(tmp_path);r=ExperienceFeedbackGateway(s).record_failed('x',['tool'],'failed');assert r['recorded'] and not r['success']
