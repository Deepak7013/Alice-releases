from alice.capabilities.recovery import CapabilityRecovery

def test_transient_errors_are_not_misclassified_as_capability_gaps():
    r=CapabilityRecovery()
    assert r.classify("lost sys.stdin") == "transient_or_provider"
    assert r.classify("No AI provider succeeded: 402") == "transient_or_provider"

def test_missing_tool_is_capability_gap():
    r=CapabilityRecovery()
    assert r.classify("Unknown tool: export_pdf") == "capability_gap"
    assert r.classify("unknown_tool") == "capability_gap"
    assert r.classify("unavailable-tool: export_pdf") == "capability_gap"

def test_recovery_uses_acquirer_only_for_gap():
    class A:
        def acquire(self,*args,**kwargs): return {"status":"acquired"}
    r=CapabilityRecovery(A())
    out=r.recover("export pdf", "Unknown tool: export_pdf")
    assert out["attempted"] is True
    assert out["result"]["status"] == "acquired"

def test_recovery_passes_missing_name_to_registry_activation_adapter():
    calls=[]
    def registered_acquire(goal, capability="", allow_research=True):
        calls.append((goal, capability, allow_research))
        return {"status":"acquired", "activated_tool":capability}
    recovery=CapabilityRecovery(registered_acquire)

    outcome=recovery.recover("export a PDF", "unknown_tool", capability="export_pdf")

    assert calls == [("export a PDF", "export_pdf", True)]
    assert outcome == {
        "attempted":True,
        "result":{"status":"acquired", "activated_tool":"export_pdf"},
    }

def test_transient_error_never_invokes_callable_acquirer():
    calls=[]
    recovery=CapabilityRecovery(lambda *args, **kwargs: calls.append((args, kwargs)))

    outcome=recovery.recover("export a PDF", "timeout", capability="export_pdf")

    assert outcome == {"attempted":False, "reason":"transient_or_provider"}
    assert calls == []
