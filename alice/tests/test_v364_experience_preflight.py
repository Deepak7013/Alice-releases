from alice.experience.store import ExperienceStore
from alice.experience.evolution import ExperienceEvolution
from alice.executive.experience_preflight import ExperienceAwarePreflight
def test_experience_hint_is_advisory(tmp_path):
 s=ExperienceStore(tmp_path); s.record('build report',['builder'],True,'done',['verify output'])
 r=ExperienceAwarePreflight(ExperienceEvolution(s)).inspect('build report')
 assert r.hint.reusable and r.hint.examples>=1 and r.advisory_only
