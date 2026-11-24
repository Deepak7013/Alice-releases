from alice.devices.secure_messaging import SecureDeviceMessenger
def test_round_trip():
    m=SecureDeviceMessenger("secret"); p=m.create("pc","phone","hello"); assert m.read(p)["message"]=="hello"
def test_tamper_rejected():
    m=SecureDeviceMessenger("secret"); p=m.create("pc","phone","hello"); p["sig"]="bad"
    try:m.read(p)
    except ValueError:pass
    else:assert False
def test_wrong_kind_rejected():
    from alice.devices.bridge import BridgeMessage
    m=SecureDeviceMessenger("secret"); p=BridgeMessage.encode("other",{}, "secret")
    try:m.read(p)
    except ValueError:pass
    else:assert False
