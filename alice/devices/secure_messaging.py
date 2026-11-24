from __future__ import annotations
import time, uuid
from .bridge import BridgeMessage
class SecureDeviceMessenger:
    def __init__(self, secret): self.secret=secret
    def create(self, sender, recipient, message):
        payload={"id":uuid.uuid4().hex,"sender":sender,"recipient":recipient,"message":str(message),"created_at":time.time()}
        return BridgeMessage.encode("message",payload,self.secret)
    def read(self, packet):
        item=BridgeMessage.decode(packet,self.secret)
        if item.get("kind")!="message": raise ValueError("not a message packet")
        return item["payload"]
