from alice.security.device_consent import DeviceConsent

def test_device_consent_is_scoped_and_revocable(tmp_path):
 c=DeviceConsent(tmp_path); c.grant('p',['notifications','messaging']); assert c.allowed('p','messaging'); c.revoke('p','messaging'); assert not c.allowed('p','messaging')
