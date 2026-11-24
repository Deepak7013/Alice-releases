import json

from alice.builder.engine import BuilderEngine
from alice.builder.postconditions import verify_builder_project_postcondition
from alice.execution.postconditions import PostconditionRegistry
from alice.agent.executor import Executor
from alice.tools.registry import ToolRegistry


class PlanRouter:
    def __init__(self,plan):self.plan=plan
    def ask(self,_prompt):return json.dumps(self.plan)


def _engine(tmp_path,plan):
    engine=BuilderEngine(PlanRouter(plan),root=tmp_path)
    engine._test=lambda _project,commands:{"ok":True,"results":[
        {"command":commands[0],"returncode":0,"stdout":"","stderr":"",
         "sandbox":{"verified":True,"backend":"docker"}}]}
    return engine


def test_builder_requires_runnable_tests_and_hash_verified_outputs(tmp_path):
    engine=_engine(tmp_path,{"files":[{"path":"app.py","content":"print('ready')\n"}],
                             "tests":["pytest -q"],"run_command":"python app.py"})
    tools=ToolRegistry();tools.postconditions=PostconditionRegistry()
    tools.add("build_project","Build and test",lambda request,project_name,research:
        engine.build(request,project_name,research),"write")
    tools.postconditions.register("build_project",lambda args,result:
        verify_builder_project_postcondition(args,result,engine.projects))
    executor=Executor(tools);executor.permissions.needs_confirmation=lambda _name,_args:False

    result=executor.run({"steps":[{"tool":"build_project","args":{
        "request":"a tiny app","project_name":"sample","research":False}}]})[0]

    assert result["status"]=="verified"
    evidence=result["result"]["postcondition"]["evidence"]
    assert evidence["observed"] is True
    assert evidence["files_verified"]==1
    assert evidence["successful_tests"]==1
    assert evidence["isolated_tests_verified"] is True
    assert "_postcondition_context" not in result["result"]


def test_builder_postcondition_detects_tampered_file_after_report(tmp_path):
    engine=_engine(tmp_path,{"files":[{"path":"app.py","content":"print('ready')\n"}],
                             "tests":["pytest -q"]})
    result=engine.build("a tiny app",project_name="tampered",research=False,max_repair_rounds=0)
    path=engine.projects/"tampered"/"app.py"
    path.write_text("tampered",encoding="utf-8")

    check=verify_builder_project_postcondition({},result,engine.projects,"tampered")

    assert not check.ok
    assert check.reason=="builder_output_readback_mismatch"


def test_builder_refuses_a_plan_without_runnable_tests_before_writing(tmp_path):
    engine=_engine(tmp_path,{"files":[{"path":"app.py","content":"print('ready')\n"}],"tests":[]})

    result=engine.build("a tiny app",project_name="untested",research=False,max_repair_rounds=0)

    assert result["ok"] is False
    assert result["status"]=="build_plan_missing_runnable_test_or_files"
    assert not (engine.projects/"untested"/"app.py").exists()


def test_builder_postconditions_are_registered_for_both_active_builder_tools():
    from pathlib import Path
    source=(Path(__file__).resolve().parents[1]/"ui"/"app.py").read_text(encoding="utf-8")
    assert 't.postconditions.register("build_project",lambda args,result:verify_builder_project_postcondition(args,result,builder.projects,"alice-project"))' in source
    assert 't.postconditions.register("build_ai_agent",lambda args,result:verify_builder_project_postcondition(args,result,builder.projects,"alice-agent"))' in source
    assert "test_runner=DockerBuilderTestRunner()" in source


def test_builder_postcondition_rejects_tests_without_verified_isolation(tmp_path):
    engine=_engine(tmp_path,{"files":[{"path":"app.py","content":"print('ready')\n"}],
                             "tests":["pytest -q"]})
    engine._test=lambda _project,commands:{"ok":True,"results":[
        {"command":commands[0],"returncode":0,"stdout":"","stderr":""}]}
    result=engine.build("a tiny app",project_name="unsandboxed",research=False,max_repair_rounds=0)
    assert result["ok"]
    assert not verify_builder_project_postcondition({},result,engine.projects,"unsandboxed").ok
