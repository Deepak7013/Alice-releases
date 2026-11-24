from __future__ import annotations
import hashlib,json,threading
from pathlib import Path
from datetime import datetime,timezone

def _now(): return datetime.now(timezone.utc).isoformat()
class AuditChain:
    def __init__(self, path=None):
        self.path=Path(path or 'alice_workspace/runtime/security_audit.jsonl'); self.path.parent.mkdir(parents=True,exist_ok=True); self._lock=threading.Lock()
    def _last(self):
        if not self.path.exists(): return '0'*64
        lines=self.path.read_text(encoding='utf-8').splitlines()
        if not lines:return '0'*64
        try:return json.loads(lines[-1])['hash']
        except Exception:return '0'*64
    def append(self,event,**data):
        with self._lock:
            row={'time':_now(),'event':event,'data':data,'prev_hash':self._last()}
            raw=json.dumps(row,sort_keys=True,ensure_ascii=False,default=str).encode(); row['hash']=hashlib.sha256(raw).hexdigest()
            with self.path.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
            return row
    def verify(self):
        prev='0'*64
        if not self.path.exists(): return True
        for line in self.path.read_text(encoding='utf-8').splitlines():
            row=json.loads(line); stored=row.pop('hash');
            if row.get('prev_hash')!=prev:return False
            if hashlib.sha256(json.dumps(row,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()!=stored:return False
            prev=stored
        return True
