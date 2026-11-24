import json
from pathlib import Path

import pytest

from alice.gluttony.evolver import DevourEngine, DevourError
from alice.gluttony.review import DevourReviewStore


def _source(root, name, content):
    source = root / name
    source.mkdir()
    (source / "LICENSE.txt").write_text("MIT License\n", encoding="utf-8")
    (source / "agent.py").write_text(content, encoding="utf-8")
    return source


def _engine(root):
    return DevourEngine(root, self_manager=object())


def test_multi_source_devour_quarantines_compares_and_never_executes_imported_code(tmp_path):
    marker = tmp_path / "imported_code_ran.txt"
    left = _source(tmp_path, "left", f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n# planner agent tool\n")
    right = _source(tmp_path, "right", "# planner agent stream\n")
    engine = _engine(tmp_path)

    result = engine.devour_many([str(left), str(right)])
    report = json.loads(Path(result["report"]).read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert report["status"] == "analyzed"
    assert report["source_count"] == 2
    assert len({row["quarantine"] for row in report["sources"]}) == 2
    assert all(Path(row["report"]).is_file() for row in report["sources"])
    assert all(row["license"]["kind"] == "MIT" for row in report["sources"])
    assert report["license_comparison"]["consistent_detected_license"] is True
    assert len(report["source_quality_comparison"]["per_source"])==2
    assert report["source_quality_comparison"]["compatibility_comparison"]["external_code_executed"] is False
    assert report["source_quality_comparison"]["dependency_comparison"]["union"]==[]
    assert report["policy"]["executed_external_code"] is False
    assert report["policy"]["promotion_enabled"] is False
    assert report["policy"]["auto_upgrade_enabled"] is False
    assert all(not candidate["approval"]["approved"] for candidate in result["capability_candidates"])
    assert not marker.exists()
    assert engine.verify_multi_postcondition({"sources": [str(left), str(right)]}, result).ok


def test_multi_source_quality_comparison_reports_dependency_conflicts_and_runtime_limits(tmp_path):
    first=_source(tmp_path,"dependency_a","# planner agent tool\n")
    second=_source(tmp_path,"dependency_b","# planner agent stream\n")
    (first/"requirements.txt").write_text("requests==2.32.0\n",encoding="utf-8")
    (second/"requirements.txt").write_text("requests>=2.0\n",encoding="utf-8")
    engine=_engine(tmp_path)

    result=engine.devour_many([str(first),str(second)])
    report=json.loads(Path(result["report"]).read_text(encoding="utf-8"))
    comparison=report["source_quality_comparison"]

    assert len(comparison["per_source"])==2
    assert comparison["dependency_comparison"]["conflicting_specifications"]==[
        {"ecosystem":"python","name":"requests","specifications":["==2.32.0",">=2.0"]}]
    assert comparison["compatibility_comparison"]["external_code_executed"] is False
    assert all("static signals only" in row["assessment"]
        for row in comparison["compatibility_comparison"]["per_source"])
    assert engine.verify_multi_postcondition({"sources":[str(first),str(second)]},result).ok


def test_multi_source_digest_is_deterministic_and_order_sensitive(tmp_path):
    first = _source(tmp_path, "first", "# planner\n")
    second = _source(tmp_path, "second", "# workspace filesystem\n")
    engine = _engine(tmp_path)

    forward = engine.devour_many([str(first), str(second)])
    forward_again = engine.devour_many([str(first), str(second)])
    reversed_order = engine.devour_many([str(second), str(first)])

    assert forward["combined_tree_sha256"] == forward_again["combined_tree_sha256"]
    assert forward["combined_tree_sha256"] != reversed_order["combined_tree_sha256"]


@pytest.mark.parametrize("sources", [[], ["only-one"], ["same", "same"], ["x"] * 9, "not-a-list"])
def test_multi_source_devour_rejects_invalid_count_or_duplicate_input(tmp_path, sources):
    with pytest.raises(DevourError):
        _engine(tmp_path).devour_many(sources)


def test_multi_source_postcondition_rehashes_quarantine_and_rejects_tampering(tmp_path):
    first = _source(tmp_path, "first", "# planner\n")
    second = _source(tmp_path, "second", "# agent\n")
    engine = _engine(tmp_path)
    args = {"sources": [str(first), str(second)]}
    result = engine.devour_many(args["sources"])
    success = engine.verify_multi_postcondition(args, result)
    assert success.ok is True

    report = json.loads(Path(result["report"]).read_text(encoding="utf-8"))
    acquired = Path(report["sources"][0]["acquired_source"])
    (acquired / "agent.py").write_text("# changed after report\n", encoding="utf-8")

    rejected = engine.verify_multi_postcondition(args, result)
    assert rejected.ok is False
    assert rejected.evidence["observed"] is False


@pytest.mark.parametrize("section", [
    "capability_comparison",
    "license_comparison",
    "provenance_comparison",
    "source_quality_comparison",
])
def test_multi_source_postcondition_recomputes_aggregate_summaries(tmp_path, section):
    first = _source(tmp_path, "first", "# planner agent\n")
    second = _source(tmp_path, "second", "# planner stream\n")
    engine = _engine(tmp_path)
    args = {"sources": [str(first), str(second)]}
    result = engine.devour_many(args["sources"])
    report_path = Path(result["report"])
    report = json.loads(report_path.read_text(encoding="utf-8"))

    if section == "capability_comparison":
        report[section]["candidate_union"] = []
    elif section == "license_comparison":
        report[section]["consistent_detected_license"] = False
    elif section == "provenance_comparison":
        report[section]["per_source"][0]["source_identity"] = "forged/source"
    else:
        report[section]["dependency_comparison"]["union"] = [{"ecosystem":"python","name":"forged"}]
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    rejected = engine.verify_multi_postcondition(args, result)
    assert rejected.ok is False
    assert rejected.evidence["observed"] is False


def test_multi_source_postcondition_recomputes_child_security_and_capabilities(tmp_path):
    first = _source(tmp_path, "first", "# planner agent\n")
    second = _source(tmp_path, "second", "# planner stream\n")
    engine = _engine(tmp_path)
    args = {"sources": [str(first), str(second)]}
    result = engine.devour_many(args["sources"])
    report = json.loads(Path(result["report"]).read_text(encoding="utf-8"))
    child_path = Path(report["sources"][0]["report"])
    child = json.loads(child_path.read_text(encoding="utf-8"))
    child["security"]["threat_count"] += 1
    child_path.write_text(json.dumps(child, indent=2) + "\n", encoding="utf-8")

    rejected = engine.verify_multi_postcondition(args, result)
    assert rejected.ok is False
    assert rejected.evidence["observed"] is False

    # Restore a fresh job, then alter only the analyzer's aggregate candidate claim.
    second_job = engine.devour_many(args["sources"])
    second_report = json.loads(Path(second_job["report"]).read_text(encoding="utf-8"))
    child_path = Path(second_report["sources"][0]["report"])
    child = json.loads(child_path.read_text(encoding="utf-8"))
    child["capability_candidates"] = []
    child_path.write_text(json.dumps(child, indent=2) + "\n", encoding="utf-8")

    rejected = engine.verify_multi_postcondition(args, second_job)
    assert rejected.ok is False
    assert rejected.evidence["observed"] is False


def test_multi_source_devour_has_no_auto_upgrade_argument(tmp_path):
    first = _source(tmp_path, "first", "# one\n")
    second = _source(tmp_path, "second", "# two\n")
    with pytest.raises(TypeError):
        _engine(tmp_path).devour_many([str(first), str(second)], auto_upgrade=True)


def test_multi_source_report_supports_individual_review_and_native_evidence(tmp_path):
    first = _source(tmp_path, "first", "# planner agent tool\n")
    second = _source(tmp_path, "second", "# planner agent stream\n")
    engine = _engine(tmp_path)
    result = engine.devour_many([str(first), str(second)])
    report = json.loads(Path(result["report"]).read_text(encoding="utf-8"))
    review = DevourReviewStore(tmp_path)

    assert review.latest_report_path() == Path(result["report"])
    state = review.inspect(result["report"])
    assert state["multi_source"] is True
    assert len(state["source_trees"]) == 2
    assert len(state["source_details"]) == 2
    assert all(not row["approved"] for row in state["capabilities"])
    assert state["license"]["kind"] == "MIT"
    assert state["security"]["files_scanned"] >= 2

    capability = state["capabilities"][0]["name"]
    review.approve_capability(result["report"], capability, confirmed=True)
    evidence = review.approval_evidence(result["report"], [capability])
    assert evidence["report_sha256"] == state["report_sha256"]
    assert evidence["tree_sha256"] == report["combined_tree_sha256"]
    assert evidence["source_tree_sha256s"] == state["source_trees"]
    assert evidence["approvals"][0]["source_tree_sha256s"] == state["source_trees"]
    assert evidence["provenance"]["external_code_executed"] is False
    assert [row["name"] for row in evidence["native_evidence"]["candidates"]] == [capability]
    assert evidence["native_evidence"]["samples"]
    assert all(sample["path"].startswith("source_") for sample in evidence["native_evidence"]["samples"])

    other = next(row["name"] for row in state["capabilities"] if row["name"] != capability)
    with pytest.raises(ValueError, match="individual approval"):
        review.approval_evidence(result["report"], [other])


def test_multi_source_review_rejects_changed_child_after_approval(tmp_path):
    first = _source(tmp_path, "first", "# planner agent tool\n")
    second = _source(tmp_path, "second", "# planner agent stream\n")
    engine = _engine(tmp_path)
    result = engine.devour_many([str(first), str(second)])
    report = json.loads(Path(result["report"]).read_text(encoding="utf-8"))
    review = DevourReviewStore(tmp_path)
    capability = review.inspect(result["report"])["capabilities"][0]["name"]
    review.approve_capability(result["report"], capability, confirmed=True)

    acquired = Path(report["sources"][1]["acquired_source"])
    (acquired / "agent.py").write_text("# altered after review\n", encoding="utf-8")
    with pytest.raises(ValueError, match="independent verification"):
        review.approval_evidence(result["report"], [capability])


def test_multi_source_review_rejects_child_report_path_outside_devour_store(tmp_path):
    first = _source(tmp_path, "path_first", "# planner agent tool\n")
    second = _source(tmp_path, "path_second", "# planner agent stream\n")
    result = _engine(tmp_path).devour_many([str(first), str(second)])
    aggregate_path = Path(result["report"])
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    outside = tmp_path / "outside_child_report.json"
    outside.write_text(json.dumps({"status": "analyzed", "tree_sha256": "0" * 64}), encoding="utf-8")
    aggregate["sources"][0]["report"] = str(outside)
    aggregate_path.write_text(json.dumps(aggregate), encoding="utf-8")

    with pytest.raises(Exception, match="child report|quarantine|aggregate"):
        DevourReviewStore(tmp_path).inspect(aggregate_path)
