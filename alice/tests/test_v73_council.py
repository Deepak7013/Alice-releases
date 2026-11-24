from alice.agents import AgentCouncil, SpecialistResult

def test_council_consensus_and_disagreement():
    c=AgentCouncil({'a':lambda q: SpecialistResult('a','yes',.9), 'b':lambda q: SpecialistResult('b','yes',.8), 'c':lambda q: SpecialistResult('c','no',1.0)})
    d=c.consult('q'); assert d.answer=='yes'; assert d.contributors==['a','b']; assert d.disagreements==['c']

def test_specialist_output_contract():
    c=AgentCouncil({'x':lambda q:'bad'})
    try: c.consult('q'); assert False
    except TypeError: pass

def test_unknown_specialist_rejected():
    c=AgentCouncil({'x':lambda q: SpecialistResult('x','ok',1)})
    try: c.consult('q',['missing']); assert False
    except KeyError: pass
