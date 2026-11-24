import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from alice.gluttony.assimilation import AssimilationEngine
from alice.gluttony.discovery import DiscoveryError, GitHubRepositoryDiscovery
from alice.gluttony.evolver import DevourEngine
from alice.gluttony.intake import LocalInputAdapter


class Response:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.payload[:limit]


def repo(name, *, stars, license_id="MIT", pushed_at=None, archived=False, url=None):
    return {
        "full_name": name,
        "html_url": url or f"https://github.com/{name}",
        "description": "candidate",
        "language": "Python",
        "stargazers_count": stars,
        "forks_count": 1,
        "open_issues_count": 2,
        "pushed_at": pushed_at or datetime.now(timezone.utc).isoformat(),
        "archived": archived,
        "fork": False,
        "private": False,
        "disabled": False,
        "license": {"spdx_id": license_id, "name": license_id},
    }


def test_public_repository_candidates_are_ranked_and_remain_unselected():
    payload = json.dumps({"total_count": 3, "incomplete_results": False, "items": [
        repo("owner/active", stars=500),
        repo("owner/archived", stars=9000, license_id=None, archived=True,
             pushed_at="2018-01-01T00:00:00Z"),
        {"full_name": "owner/private-link", "html_url": "https://evil.example/x",
         "private": False, "license": None},
    ]}).encode()
    seen = {"urls": []}

    def opener(request, timeout):
        seen["url"] = request.full_url
        seen["urls"].append(request.full_url)
        seen["headers"] = request.headers
        seen["timeout"] = timeout
        return Response(payload)

    result = GitHubRepositoryDiscovery(opener=opener).discover("Android accessibility observer", limit=4)

    assert result["candidates"][0]["name"] == "owner/active"
    assert [c["rank"] for c in result["candidates"]] == [1, 2]
    assert result["candidates"][0]["license"]["review_required"] is True
    assert result["candidates"][0]["discovery_signals"] == ["stars", "updated"]
    assert "no candidate is selected" in result["policy"]
    assert len(seen["urls"]) == 2
    assert any("sort=stars" in url for url in seen["urls"])
    assert any("sort=updated" in url for url in seen["urls"])
    assert seen["headers"]["Accept"] == "application/vnd.github+json"
    assert seen["timeout"] == 15


def test_objective_relevance_can_outweigh_raw_popularity_when_ranking_sources():
    relevant=repo("owner/offline-speech-transcription",stars=5)
    relevant["description"]="Offline speech transcription reference implementation"
    popular=repo("owner/general-framework",stars=100000)
    popular["description"]="A general software framework"
    payload=json.dumps({"total_count":2,"incomplete_results":False,"items":[popular,relevant]}).encode()
    result=GitHubRepositoryDiscovery(opener=lambda *_args,**_kwargs:Response(payload)).discover(
        "offline speech transcription",limit=2)

    assert result["candidates"][0]["name"]=="owner/offline-speech-transcription"
    assert result["candidates"][0]["relevance_score"]>result["candidates"][1]["relevance_score"]
    assert result["candidates"][0]["discovery_score"]>result["candidates"][1]["discovery_score"]


@pytest.mark.parametrize("query,limit", [(" ", 5), ("valid capability", 0), ("valid capability", True)])
def test_discovery_rejects_invalid_query_or_limit(query, limit):
    with pytest.raises(DiscoveryError):
        GitHubRepositoryDiscovery(opener=lambda *_args, **_kwargs: None).discover(query, limit=limit)


def test_devour_persists_discovery_report_without_selecting_a_repo(tmp_path):
    class Discovery:
        def discover(self, query, *, limit):
            return {"query": query, "candidates": [], "policy": "no automatic selection"}

    engine = DevourEngine(
        tmp_path,
        gluttony=AssimilationEngine(tmp_path),
        self_manager=object(),
        discovery=Discovery(),
    )
    result = engine.discover_candidates("offline speech recognition")

    report = json.loads(Path(result["report"]).read_text(encoding="utf-8"))
    assert result["candidates"] == []
    assert report["query"] == "offline speech recognition"
    assert list(engine.base.glob("DISCOVERY_*.json"))


def test_objective_devour_selects_ranked_public_sources_without_manual_repo_input(tmp_path):
    ranked=[
        {"rank":1,"name":"owner/top","url":"https://github.com/owner/top","score":70,
         "discovery_score":82,"relevance_score":100,"stars":200,"language":"Python",
         "license":{"spdx_id":"MIT"}},
        {"rank":2,"name":"owner/next","url":"https://github.com/owner/next","score":60,
         "discovery_score":76,"relevance_score":100,"stars":100,"language":"Python",
         "license":{"spdx_id":"Apache-2.0"}},
        {"rank":3,"name":"owner/last","url":"https://github.com/owner/last","score":90,
         "discovery_score":30,"relevance_score":0,"stars":9000,"language":"Python",
         "license":{"spdx_id":"Unknown"}},
    ]

    class Discovery:
        def discover(self, query, *, limit):
            return {"query":query,"candidates":ranked[:limit],"policy":"advisory"}

    engine=DevourEngine(tmp_path,gluttony=AssimilationEngine(tmp_path),self_manager=object(),discovery=Discovery())
    observed={}
    def fake_devour_many(sources):
        observed["sources"]=list(sources)
        report=engine.base/"MULTI_DIGEST_test_objective.json"
        report.write_text("{}",encoding="utf-8")
        return {"ok":True,"status":"analyzed","report":str(report),
            "source_count":len(sources),"policy":{"executed_external_code":False}}
    engine.devour_many=fake_devour_many

    result=engine.devour_objective("Python offline speech transcription",candidate_limit=3,source_count=2)

    assert observed["sources"]==[ranked[0]["url"],ranked[1]["url"]]
    assert result["analysis_type"]=="multi_source"
    assert result["objective_policy"]["approved_capability_count"]==0
    workflow=json.loads(Path(result["objective_workflow_report"]).read_text(encoding="utf-8"))
    assert workflow["objective"]=="Python offline speech transcription"
    assert workflow["analysis_report"]==result["report"]
    assert [row["url"] for row in workflow["selected_candidates"]]==observed["sources"]
    assert workflow["policy"]["executed_external_code"] is False


def test_objective_devour_postcondition_rechecks_discovery_selection_and_quarantine(tmp_path):
    source_a=tmp_path/"source_a"; source_a.mkdir()
    source_b=tmp_path/"source_b"; source_b.mkdir()
    (source_a/"agent.py").write_text("# planner agent tool\n",encoding="utf-8")
    (source_b/"agent.py").write_text("# planner agent streaming\n",encoding="utf-8")
    urls=["https://github.com/owner/source-a","https://github.com/owner/source-b"]

    class Discovery:
        def discover(self, query, *, limit):
            return {"query":query,"candidates":[
                {"rank":1,"name":"owner/source-a","url":urls[0],"score":70,"discovery_score":80,
                 "relevance_score":100,"stars":20,"language":"Python","license":{"spdx_id":"MIT"}},
                {"rank":2,"name":"owner/source-b","url":urls[1],"score":60,"discovery_score":75,
                 "relevance_score":100,"stars":10,"language":"Python","license":{"spdx_id":"MIT"}}],
                "policy":"advisory"}

    engine=DevourEngine(tmp_path,gluttony=AssimilationEngine(tmp_path),self_manager=object(),discovery=Discovery())
    local_by_url=dict(zip(urls,[source_a,source_b]))
    def acquire(url,slot,*,max_bytes,max_files):
        adapter=LocalInputAdapter(max_files=max_files,max_total_bytes=max_bytes)
        return engine._copy_local(local_by_url[url],slot,intake=adapter)
    engine.gluttony._acquire=acquire

    result=engine.devour_objective("agent planning and streaming",candidate_limit=2,source_count=2)
    checked=engine.verify_objective_postcondition({"objective":"agent planning and streaming"},result)

    assert result["analysis_type"]=="multi_source"
    assert checked.ok is True
    workflow=Path(result["objective_workflow_report"])
    data=json.loads(workflow.read_text(encoding="utf-8"))
    data["selected_candidates"][0]["url"]="https://github.com/attacker/other"
    workflow.write_text(json.dumps(data),encoding="utf-8")
    assert engine.verify_objective_postcondition({"objective":"agent planning and streaming"},result).ok is False


def test_reimplementation_plan_has_measurable_checks_and_live_capability_evidence(tmp_path):
    class Capabilities:
        def get(self, name):
            return {"name": name, "verified": True}

        def status(self, name):
            return {"name": name, "known": True, "status": "available",
                    "verified": True, "reliability": 0.9}

    engine = DevourEngine(
        tmp_path, gluttony=AssimilationEngine(tmp_path), self_manager=object(),
        capability_manager=Capabilities(),
    )
    plan, _ = engine._capability_plan(
        [{"name": "tool_orchestration", "evidence_score": 2,
          "evidence_terms": ["tool", "plugin"], "evidence_files": ["src/tools.py"]}],
        {"tests": ["tests/test_tools.py"],
         "project": {"test_files": ["tests/test_tools.py"],
                     "dependencies": [{"name": "pytest"}]}},
        {"kind": "MIT"},
    )

    specification = plan[0]["specification"]
    assert specification["candidate_test_files"] == ["tests/test_tools.py"]
    assert specification["declared_dependency_count"] == 1
    assert {criterion["check"] for criterion in specification["acceptance_criteria"]} >= {
        "native_implementation_tests_pass", "external_candidate_code_never_executes",
        "capability_registry_records_provenance_and_evidence",
    }
    assert plan[0]["alice_live_capability"]["verified"] is True
    assert specification["evidence_files"] == ["src/tools.py"]
