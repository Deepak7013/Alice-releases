from alice.devices.pairing import PairingManager

def test_pairing_is_one_time():
 p=PairingManager(); c=p.create_code('d1'); assert p.verify('d1',c); assert not p.verify('d1',c)
