from alice.horizon import HorizonManager
def test_checkpoint_recovery(tmp_path):
 h=HorizonManager(tmp_path); p=h.create('g'); h.checkpoint(p['id'],'start',{'x':1},verified=True); assert h.latest_verified(p['id'])['label']=='start'; assert h.recover(p['id'])['recovery_available']
def test_no_unverified_recovery(tmp_path):
 h=HorizonManager(tmp_path); p=h.create('g'); h.checkpoint(p['id'],'bad',{},verified=False)
 try:h.recover(p['id'])
 except RuntimeError:pass
 else:assert False
