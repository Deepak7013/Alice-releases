from alice.council import CouncilEngine
def test_council_is_auditable_and_nonexecuting():
 c=CouncilEngine({'research':lambda t:'A','critic':lambda t:'B'}); r=c.deliberate('x',2); assert len(r['proposals'])==2; assert r['requires_verification'] and r['digest']
def test_failed_role_isolated():
 c=CouncilEngine({'good':lambda t:'ok','bad':lambda t:1/0}); r=c.deliberate('x',2); assert r['agreement']==.5 and r['proposals'][1]['ok'] is False
