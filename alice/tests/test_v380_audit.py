from alice.engineering.audit import EngineeringAudit
def test_audit_persists_and_is_bounded(tmp_path):
 a=EngineeringAudit(tmp_path,2); a.record('candidate',{'ok':True}); a.record('validation',{'ok':True}); a.record('promotion',{'ok':False}); assert len(a.list())==2 and len(a.list('promotion'))==1
 b=EngineeringAudit(tmp_path,2); assert len(b.list())==2
