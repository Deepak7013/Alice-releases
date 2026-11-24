from alice.devices.transfer import TransferManager

def test_transfer_integrity():
 t=TransferManager(); p=t.prepare(b'alice'); assert t.verify(p); p['data']=b'evil'; assert not t.verify(p)
