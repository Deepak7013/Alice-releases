from __future__ import annotations
import json,hmac,hashlib
class BridgeMessage:
    @staticmethod
    def encode(kind,payload,secret):
        body=json.dumps({'kind':kind,'payload':payload},sort_keys=True,separators=(',',':')).encode(); sig=hmac.new(secret.encode(),body,hashlib.sha256).hexdigest(); return {'body':body.decode(),'sig':sig}
    @staticmethod
    def decode(packet,secret):
        body=packet['body'].encode(); expected=hmac.new(secret.encode(),body,hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,packet['sig']): raise ValueError('invalid bridge signature')
        return json.loads(body)
class LocalBridge:
    def __init__(self,secret): self.secret=secret
    def pack(self,kind,payload): return BridgeMessage.encode(kind,payload,self.secret)
    def unpack(self,packet): return BridgeMessage.decode(packet,self.secret)
