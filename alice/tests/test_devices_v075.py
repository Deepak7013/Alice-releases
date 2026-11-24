from alice.devices.registry import DeviceRegistry

def test_device_registry_persists_and_finds_capability(tmp_path):
 r=DeviceRegistry(tmp_path); d=r.register('Phone','android',['notifications','adb']); r.pair(d['id']); r.set_online(d['id'])
 r2=DeviceRegistry(tmp_path); assert r2.get(d['id'])['paired']; assert r2.find_capability('notifications')[0]['id']==d['id']
