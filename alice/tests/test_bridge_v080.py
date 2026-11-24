from alice.devices.bridge import LocalBridge

def test_bridge_rejects_tampering():
 b=LocalBridge('secret'); p=b.pack('ping',{'x':1}); assert b.unpack(p)['payload']['x']==1; p['body']=p['body'].replace('1','2');
 try:b.unpack(p); assert False
 except ValueError:pass
