from alice.providers.runtime_policy import RuntimePolicy

def test_local_first_prefers_local():
    p=RuntimePolicy("local_first",True)
    assert p.order(["openrouter","local","openai"],local_ready=True)==["local","openrouter","openai"]

def test_local_required_blocks_remote_when_unavailable():
    p=RuntimePolicy("local_required",False)
    assert p.order(["openrouter","local"],local_ready=False)==[]

def test_local_required_allows_only_local_when_ready():
    p=RuntimePolicy("local_required",False)
    assert p.order(["openrouter","local","openai"],local_ready=True)==["local"]
