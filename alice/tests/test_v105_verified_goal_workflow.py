from pathlib import Path

import pytest

from alice.agent.agent import AliceAgent
from alice.execution.postconditions import PostconditionRegistry, PostconditionResult
from alice.goals import GoalEngine
from alice.goals.verified_workflow import VerifiedGoalWorkflow
from alice.horizon.task_continuity import TaskContinuityStore
from alice.learning.engine import LearningEngine
from alice.runtime import AliceRuntime
from alice.tools.registry import ToolRegistry
from alice.agent.executor import Executor as AgentExecutor
from alice.world.model import WorldModel


class ExecutorAgent:
    def __init__(self, executor, path, *, with_verifier=True):
        self.executor=executor
        self.plan={"steps":[{"tool":"write_file","args":{"path":str(path),"content":"verified"}}]}

    def run_with_outcome(self, _request):
        return AliceAgent._task_outcome("step finished",self.executor.run(self.plan))


class NeverRunAgent:
    def run_with_outcome(self, _request):
        raise AssertionError("restart recovery must not repeat an action")


def _setup(root, *, with_verifier=True, crash_goal_completion=False):
    destination=root/"workspace"/"proof.txt"

    def write_file(path,content):
        target=Path(path); target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(content,encoding="utf-8")
        return {"ok":True,"path":str(target)}

    tools=ToolRegistry()
    tools.add("write_file","Write one workspace file",write_file,"write")
    tools.postconditions=PostconditionRegistry()
    if with_verifier:
        def verify_write(args,result):
            path=Path(args["path"])
            observed=result.get("path")==str(path) and path.is_file() and path.read_text(encoding="utf-8")==args["content"]
            return PostconditionResult(observed,{"observed":True,"content_matches":observed})
        tools.postconditions.register("write_file",verify_write)
    executor=AgentExecutor(tools)
    executor.permissions.needs_confirmation=lambda _name,_args:False
    world=WorldModel(root)
    runtime=AliceRuntime(root=root,agent=ExecutorAgent(executor,destination),agency=False,world=world)
    learning=LearningEngine(root)
    runtime.events.subscribe("task.completed",learning.record_verified_runtime_outcome)
    goals=GoalEngine(root)
    goal=goals.create("Write proof","write a verified proof file")
    step=goals.add_step(goal["id"],"Write proof",request="Write proof.txt")
    workflow=VerifiedGoalWorkflow(root,runtime,goals=goals,world=world)
    if crash_goal_completion:
        def crash(*_args,**_kwargs):
            raise RuntimeError("simulated interruption after durable verified checkpoint")
        goals.complete_step=crash
    return workflow,goal,step,destination,runtime


def test_goal_step_completes_and_learning_checkpoint_survive_restart(tmp_path):
    workflow,goal,step,destination,_runtime=_setup(tmp_path)

    result=workflow.run_step(goal["id"],step["id"])

    assert result["status"]=="completed"
    assert result["verified"] is True
    assert destination.read_text(encoding="utf-8")=="verified"
    restored_goal=GoalEngine(tmp_path).status(goal["id"])["goal"]
    assert restored_goal["status"]=="completed"
    assert restored_goal["steps"][0]["status"]=="completed"
    task=TaskContinuityStore(tmp_path).get(result["task_id"])
    assert task["status"]=="completed"
    assert task["checkpoints"][-1]["verified"] is True
    assert LearningEngine(tmp_path).stats()["experience_records"]==1
    world=WorldModel(tmp_path)
    runtime_outcome=world.truth("tasks","latest_runtime_outcome")
    goal_outcome=world.get_entity("tasks",f"goal:{goal['id']}:step:{step['id']}")
    assert runtime_outcome["value"]["verified"] is True
    assert goal_outcome["data"]["status"]=="completed"
    assert goal_outcome["data"]["verified"] is True


def test_interrupted_goal_reconciles_verified_checkpoint_without_repeating_action(tmp_path):
    workflow,goal,step,destination,_runtime=_setup(tmp_path,crash_goal_completion=True)
    with pytest.raises(RuntimeError,match="simulated interruption"):
        workflow.run_step(goal["id"],step["id"])
    assert destination.read_text(encoding="utf-8")=="verified"

    recovered=VerifiedGoalWorkflow(tmp_path,AliceRuntime(root=tmp_path,agent=NeverRunAgent(),agency=False))
    result=recovered.run_step(goal["id"],step["id"])

    assert result["status"]=="completed"
    assert result["recovered_from_checkpoint"] is True
    assert GoalEngine(tmp_path).status(goal["id"])["goal"]["status"]=="completed"
    assert len(LearningEngine(tmp_path).store.records)==1


def test_unverified_side_effect_fails_goal_and_never_creates_positive_learning(tmp_path):
    workflow,goal,step,destination,_runtime=_setup(tmp_path,with_verifier=False)

    result=workflow.run_step(goal["id"],step["id"])

    assert destination.is_file()  # The write happened, but no independent observer verified it.
    assert result["status"]=="failed_verification"
    assert result["verified"] is False
    assert GoalEngine(tmp_path).status(goal["id"])["goal"]["status"]=="failed"
    task=TaskContinuityStore(tmp_path).get(result["task_id"])
    assert task["status"]=="failed"
    assert not task["checkpoints"][-1]["verified"]
    assert LearningEngine(tmp_path).stats()["experience_records"]==0
    step_state=WorldModel(tmp_path).get_entity("tasks",f"goal:{goal['id']}:step:{step['id']}")
    assert step_state["data"]["status"]=="failed"
    assert step_state["data"]["verified"] is False
