from alice.providers.health_memory import ProviderHealthMemory

def test_health_memory_persists(tmp_path):
    p=tmp_path/"h.json"; h=ProviderHealthMemory(p); h.record("local",ok=True,latency=1.0); h.record("local",ok=False,error="x")
    h2=ProviderHealthMemory(p); row=h2.snapshot()["local"]
    assert row["success"]==1 and row["failure"]==1 and row["last_error"]=="x"
