from __future__ import annotations
import hashlib,hmac,secrets,time
class PairingManager:
    def __init__(self, ttl_seconds=300): self.ttl=ttl_seconds; self.pending={}
    def create_code(self,device_id):
        code=f"{secrets.randbelow(1000000):06d}"; self.pending[device_id]=(code,time.time()+self.ttl); return code
    def verify(self,device_id,code):
        item=self.pending.get(device_id)
        if not item or time.time()>item[1]: return False
        ok=hmac.compare_digest(item[0],str(code));
        if ok: self.pending.pop(device_id,None)
        return ok
    @staticmethod
    def fingerprint(secret): return hashlib.sha256(secret.encode()).hexdigest()[:16]
