from alice.research.pipeline import ResearchPipeline,ResearchSource
def test_research_pipeline():
 p=ResearchPipeline(lambda x: ResearchSource(x,'Title','useful evidence')); r=p.run('question',['a']); assert r.findings and r.uncertainty
def test_research_requires_question():
 try: ResearchPipeline().run(' ',[]); assert False
 except ValueError: pass
