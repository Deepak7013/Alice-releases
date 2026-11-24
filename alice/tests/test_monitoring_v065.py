import time
from alice.monitoring import MonitoringStore,MonitoringEngine
def test_deadline_notification(tmp_path):
 s=MonitoringStore(tmp_path); s.add_watch('deadline','submit',due_at=100); e=MonitoringEngine(s,now=lambda:101); out=e.tick(); assert len(out)==1; assert len(s.notifications(True))==1
def test_recurring_waits_for_interval(tmp_path):
 s=MonitoringStore(tmp_path); s.add_watch('recurring','ping',interval_seconds=60); now=[100]; e=MonitoringEngine(s,now=lambda:now[0]); assert len(e.tick())==1; now[0]=150; assert not e.tick(); now[0]=160; assert e.tick()
