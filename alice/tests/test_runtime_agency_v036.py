import tempfile
from alice.runtime import AliceRuntime

class FailingAgent:
    def run(self, request):
        raise RuntimeError("boom")

def test_runtime_exposes_agency_and_records_task_failure():
    with tempfile.TemporaryDirectory() as d:
        rt=AliceRuntime(root=d, agent=FailingAgent())
        g=rt.agency.create_goal("Finish task")
        result=rt.submit("do the thing")
        assert result["status"] == "failed"
        obs=rt.agency.recent_observations(5)
        assert any(x["event"] == "task_failed" for x in obs)
        decisions=rt.agency.observe("task_failed")
        assert any(x["goal_id"] == g["id"] for x in decisions)
