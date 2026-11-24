import json
from pathlib import Path

import pytest

from alice.gluttony.review import DevourReviewError, DevourReviewStore
from alice.security.ingest_guard import IngestGuard


def _report(root):
    base=root/"alice_workspace"/"gluttony"/"devour"
    quarantine=base/"job_review"
    acquired=quarantine/"source"
    acquired.mkdir(parents=True)
    (acquired/"agent.py").write_text("# quarantined source evidence\n",encoding="utf-8")
    guard=IngestGuard()
    report={"status":"digested","source":"https://example.test/project",
        "source_label":"example/project","quarantine":str(quarantine),
        "acquired_source":str(acquired),"tree_sha256":guard.digest_tree(acquired),
        "security":guard.scan_tree(acquired),"license":{"kind":"MIT","files":["LICENSE"],"review_required":False},
        "capability_candidates":[
            {"name":"browser_reader","evidence_score":4,"evidence_terms":["page text"],"evidence_files":["agent.py"]},
            {"name":"form_filler","evidence_score":3,"evidence_terms":["input field"],"evidence_files":["agent.py"]}],
        "policy":{"executed_external_code":False,"activated_external_code":False,"native_reimplementation_required":True},
        "alice_capability_assessment":{"capabilities":[
            {"name":"browser_reader","recommendation":"improve_native_capability"},
            {"name":"form_filler","recommendation":"reimplement_natively"}]}}
    path=base/"DIGEST_review.json"
    path.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return path,acquired


def test_capabilities_require_individual_explicit_approval_and_persist(tmp_path):
    report,_acquired=_report(tmp_path)
    review=DevourReviewStore(tmp_path)

    before=review.inspect(report)
    assert [row["name"] for row in before["capabilities"]]==["browser_reader","form_filler"]
    assert all(not row["approved"] for row in before["capabilities"])
    with pytest.raises(DevourReviewError,match="confirmation"):
        review.approve_capability(report,"browser_reader",confirmed=False)

    review.approve_capability(report,"browser_reader",confirmed=True)
    assert review.approval_evidence(report,["browser_reader"])["approvals"][0]["capability"]=="browser_reader"
    with pytest.raises(DevourReviewError,match="individual approval"):
        review.approval_evidence(report,["form_filler"])

    reloaded=DevourReviewStore(tmp_path)
    state=reloaded.inspect(report)
    assert state["capabilities"][0]["approved"] is True
    assert state["capabilities"][1]["approved"] is False


@pytest.mark.parametrize("decision", sorted(DevourReviewStore.DECISIONS))
def test_review_records_one_explicit_capability_strategy(tmp_path,decision):
    report,_acquired=_report(tmp_path)
    review=DevourReviewStore(tmp_path)
    review.approve_capability(report,"browser_reader",confirmed=True,decision=decision)

    state=review.inspect(report)
    evidence=review.approval_evidence(report,["browser_reader"])

    assert state["capabilities"][0]["decision"]==decision
    assert evidence["decisions"]=={"browser_reader":decision}
    assert evidence["approvals"][0]["decision"]==decision


def test_review_rejects_unsupported_capability_strategy(tmp_path):
    report,_acquired=_report(tmp_path)
    with pytest.raises(DevourReviewError,match="supported per-capability"):
        DevourReviewStore(tmp_path).approve_capability(report,"browser_reader",confirmed=True,
            decision="execute_imported_code")


def test_revoke_is_durable_and_report_mutation_invalidates_prior_approval(tmp_path):
    report,_acquired=_report(tmp_path)
    review=DevourReviewStore(tmp_path)
    review.approve_capability(report,"browser_reader",confirmed=True)
    review.revoke_capability(report,"browser_reader",confirmed=True)
    assert not review.inspect(report)["capabilities"][0]["approved"]
    with pytest.raises(DevourReviewError,match="individual approval"):
        review.approval_evidence(report,["browser_reader"])

    review.approve_capability(report,"browser_reader",confirmed=True)
    data=json.loads(report.read_text(encoding="utf-8"))
    data["capability_candidates"][0]["evidence_score"]=99
    report.write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8")
    with pytest.raises(DevourReviewError,match="individual approval"):
        DevourReviewStore(tmp_path).approval_evidence(report,["browser_reader"])


def test_quarantine_mutation_and_corrupt_approval_ledger_fail_closed(tmp_path):
    report,acquired=_report(tmp_path)
    review=DevourReviewStore(tmp_path)
    review.approve_capability(report,"browser_reader",confirmed=True)
    (acquired/"agent.py").write_text("# changed source\n",encoding="utf-8")
    with pytest.raises(DevourReviewError,match="no longer matches"):
        review.inspect(report)

    (acquired/"agent.py").write_text("# quarantined source evidence\n",encoding="utf-8")
    review.path.write_text("not json",encoding="utf-8")
    with pytest.raises(DevourReviewError,match="refusing to overwrite"):
        review.approve_capability(report,"form_filler",confirmed=True)


def test_review_window_is_per_capability_and_candidate_install_remains_separate():
    source=(Path(__file__).resolve().parents[1]/"ui"/"app.py").read_text(encoding="utf-8")
    assert 'label="DEVOUR Review",command=self.show_devour_review' in source
    assert '"Approve one DEVOUR capability"' in source
    assert "self.devour_reviews.approve_capability(self._devour_review_path,name,confirmed=True," in source
    assert "decision=decision,ui_request=ui_request)" in source
    assert "approved_capabilities=[name]" in source
    assert 'messagebox.askyesno("Install reviewed DEVOUR candidate"' in source
    assert 'auto_upgrade=True, approval_token="USER_APPROVED_DEVOUR_UPGRADE"' not in source
    assert 'result.get("capability_evidence",[])' in source
    assert "capability evidence is saved as a candidate, not active or runtime-verified" in source
    assert 'receipt.get("candidate_sha256")!=package.get("sha256")' in source
    assert 't.postconditions.register("devour_repository",self.devour.verify_single_postcondition)' in source
    assert 't.postconditions.register("devour_objective",self.devour.verify_objective_postcondition)' in source
    assert 't.add("devour_objective"' in source
    assert 'reuse_compatible_component = use an already verified ALICE component' in source
    assert 'integrate_behind_alice_interface' in source
    assert 'implement_native_equivalent' in source


def test_devour_engine_shares_persistent_capability_manager_with_self_manager(tmp_path):
    from alice.capabilities.manager import CapabilityManager
    from alice.gluttony.evolver import DevourEngine

    manager=CapabilityManager(tmp_path)
    engine=DevourEngine(tmp_path,capability_manager=manager)

    assert engine.self_manager.capability_manager is manager
