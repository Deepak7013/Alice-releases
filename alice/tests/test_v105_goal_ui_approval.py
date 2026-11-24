from pathlib import Path
import threading

from alice.agent.executor import Executor
from alice.runtime.approval_context import is_ui_approved_action, ui_approved_action
from alice.tools.registry import ToolRegistry


def test_ui_approval_context_is_scoped_and_allows_only_current_execution_thread():
    tools=ToolRegistry()
    executed=[]
    tools.add("self_repair","Repair ALICE",lambda: executed.append("ran") or {"ok":True},"system")
    executor=Executor(tools)
    executor.permissions.request=lambda *_args: False
    plan={"steps":[{"tool":"self_repair","args":{}}]}

    denied=executor.run(plan)
    assert denied[0]["status"]=="denied"
    assert not executed

    child_observation=[]
    with ui_approved_action():
        assert is_ui_approved_action()
        thread=threading.Thread(target=lambda:child_observation.append(is_ui_approved_action()))
        thread.start(); thread.join()
        approved=executor.run(plan)
    assert child_observation==[False]
    assert approved[0]["status"]=="attempted"
    assert executed==["ran"]
    assert not is_ui_approved_action()


def test_goal_ui_requires_visible_exact_step_confirmation_and_uses_main_thread_dispatch():
    app_path=Path(__file__).parents[1]/"ui"/"app.py"
    source=app_path.read_text(encoding="utf-8")
    assert 'label="Goals & Tasks",command=self.show_goals' in source
    assert 'messagebox.askyesno("Approve goal step"' in source
    assert '"Run this exact request through ALICE now?\\n\\n"+request' in source
    assert 'self.goal_workflow.run_step(gid,sid,user_approved=True)' in source
    assert 'threading.Thread(target=work,daemon=True,name="AliceVerifiedGoalStep").start()' in source
    assert 'self._queue_ui("goal_run_complete",gid,sid,result)' in source
    assert 'self._apply_goal_run_complete(*payload)' in source
