from alice.providers.orchestration import ModelRouter

def test_router_prefers_requested_provider():
    r=ModelRouter(); r.register('a','m1',lambda q:'A',['chat']); r.register('b','m2',lambda q:'B',['chat'])
    x=r.route('hi','chat','b'); assert x.output=='B' and x.provider=='b'

def test_router_falls_back_after_provider_error():
    r=ModelRouter(); r.register('a','bad',lambda q: (_ for _ in ()).throw(RuntimeError('down')),['chat']); r.register('b','good',lambda q:'ok',['chat'])
    x=r.route('hi','chat'); assert x.success and x.output=='ok' and x.provider=='b'

def test_router_reports_no_compatible_model():
    r=ModelRouter();
    try: r.route('hi','vision'); assert False
    except LookupError: pass
