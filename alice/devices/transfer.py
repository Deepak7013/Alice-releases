from __future__ import annotations
import hashlib
class TransferManager:
    def prepare(self,data:bytes): return {'size':len(data),'sha256':hashlib.sha256(data).hexdigest(),'data':data}
    def verify(self,packet): return hashlib.sha256(packet['data']).hexdigest()==packet['sha256'] and len(packet['data'])==packet['size']
