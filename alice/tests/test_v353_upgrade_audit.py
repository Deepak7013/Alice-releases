from alice.deployment.upgrade_audit import UpgradeAudit


def test_upgrade_audit_is_bounded_and_redacts_secrets(tmp_path):
    audit = UpgradeAudit(tmp_path)
    for i in range(100):
        audit.record("stage", detail=f"token=secret-{i}", version="ALICE v3.53.0")
    data = audit.summary()
    assert data["event_count"] == 80
    assert all("secret-" not in str(e) for e in data["events"])


def test_upgrade_audit_persists_last_stage(tmp_path):
    audit = UpgradeAudit(tmp_path)
    audit.record("install", ok=True, version="ALICE v3.53.0")
    audit.record("relaunch", ok=False, version="ALICE v3.53.0", detail="health timeout")
    result = UpgradeAudit(tmp_path).summary()
    assert result["last_stage"] == "relaunch"
    assert result["last_ok"] is False
