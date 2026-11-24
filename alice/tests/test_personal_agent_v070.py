from alice.personal_agent import UnifiedPersonalAgent
def test_confirmation_gate():
 a=UnifiedPersonalAgent()
 try: a.execute_approved('send_email'); assert False
 except PermissionError: pass
 assert a.execute_approved('send_email',approved=True)['ok']
def test_brief_empty_is_safe(): assert UnifiedPersonalAgent().brief('x').goal=='x'
