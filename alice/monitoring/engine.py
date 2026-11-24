import time
class MonitoringEngine:
 def __init__(self,store,now=None): self.store=store; self.now=now or time.time
 def tick(self):
  now=self.now(); emitted=[]
  for w in self.store.watches():
   if not w.enabled: continue
   due=False
   if w.kind=='deadline' and w.due_at is not None and (w.last_run is None) and now>=w.due_at: due=True
   elif w.kind=='recurring' and w.interval_seconds is not None and (w.last_run is None or now-w.last_run>=w.interval_seconds): due=True
   elif w.kind=='condition' and w.payload.get('trigger') is True and w.last_run is None: due=True
   if due:
    n=self.store.notify(w.title,w.payload.get('body','Reminder: '+w.title),w.payload.get('severity','info'),w.watch_id); emitted.append(n)
    raw=self.store.data['watches'][w.watch_id]; raw['last_run']=now; self.store._save()
  return emitted
