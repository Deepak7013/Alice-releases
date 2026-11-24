from alice.agent.agent import AliceAgent
from alice.runtime import AliceRuntime
from alice.world.model import WorldModel
from concurrent.futures import ThreadPoolExecutor


class FixedOutcomeAgent:
    def __init__(self, outcome=None, error=None):
        self.outcome=outcome
        self.error=error

    def run_with_outcome(self, _request):
        if self.error:
            raise self.error
        return self.outcome


def _verified_outcome():
    return AliceAgent._task_outcome("done",[{
        "step":1,"tool":"write_file","status":"verified",
        "postcondition":{"ok":True,"evidence":{"observed":True,"content_matches":True}},
    }])


def test_runtime_persists_verified_world_outcome_without_raw_request_or_postcondition(tmp_path):
    world=WorldModel(tmp_path)
    runtime=AliceRuntime(root=tmp_path,agent=FixedOutcomeAgent(_verified_outcome()),agency=False,world=world)
    secret_request="write confidential-value to result.txt"

    result=runtime.submit(secret_request)

    assert result["verified"] is True
    truth=WorldModel(tmp_path).truth("tasks","latest_runtime_outcome")
    assert truth["known"] is True
    record=truth["value"]
    assert record["task_id"]==result["task_id"]
    assert record["completion_state"]=="verified"
    assert record["verified"] is True
    assert record["tools"]==["write_file"]
    assert record["request_sha256"]
    assert record["verification_evidence_sha256"]
    assert secret_request not in repr(WorldModel(tmp_path).snapshot())
    assert "content_matches" not in repr(WorldModel(tmp_path).snapshot())
    assert truth["source"]=="alice_runtime.outcome_event"


def test_runtime_world_state_does_not_turn_unverified_effect_into_success(tmp_path):
    outcome=AliceAgent._task_outcome("maybe written",[{
        "step":1,"tool":"write_file","status":"attempted",
        "postcondition":{"ok":False,"reason":"private error detail","evidence":{"observed":False}},
    }])
    world=WorldModel(tmp_path)
    runtime=AliceRuntime(root=tmp_path,agent=FixedOutcomeAgent(outcome),agency=False,world=world)

    result=runtime.submit("write an unverified item")

    record=WorldModel(tmp_path).truth("tasks","latest_runtime_outcome")["value"]
    assert result["verified"] is False
    assert record["completion_state"]=="unverified"
    assert record["verified"] is False
    assert record["verification_evidence_sha256"] is None
    assert record["failure_count"] == 1
    assert record["failure_diagnostics_sha256"]
    assert "private error detail" not in repr(record)


def test_world_write_failure_does_not_change_independently_verified_runtime_result(tmp_path):
    class BrokenWorld:
        def observe(self,*_args,**_kwargs):
            raise OSError("simulated world store failure")

    runtime=AliceRuntime(root=tmp_path,agent=FixedOutcomeAgent(_verified_outcome()),agency=False,world=BrokenWorld())

    result=runtime.submit("write verified item")

    assert result["verified"] is True
    assert result["completion_state"]=="verified"


def test_world_observation_updates_are_serialized_and_persisted(tmp_path):
    world=WorldModel(tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda n:world.observe("tasks","parallel",{"n":n}),range(24)))

    reloaded=WorldModel(tmp_path)
    observations=reloaded.observations("tasks","parallel")
    assert len(observations)==12  # WorldModel retains the bounded latest twelve per key.
    assert len({row["id"] for row in observations})==12
    assert reloaded.truth("tasks","parallel")["known"] is True
