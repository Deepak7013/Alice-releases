from alice.action.guard import ActionGuard
from alice.tools.registry import ToolRegistry

def make_tools():
 t=ToolRegistry(); t.add("read_x","read",lambda: "ok","read"); t.add("write_x","write",lambda: "ok","write"); return t

def test_preflight_rejects_unknown_tool(tmp_path):
 g=ActionGuard(make_tools())
 p={"steps":[{"tool":"missing","args":{}}]}
 r=g.preflight(p); assert not r["ok"] and r["errors"]

def test_postflight_requires_every_step_success(tmp_path):
 g=ActionGuard(make_tools())
 p={"steps":[{"tool":"read_x","args":{}},{"tool":"write_x","args":{}}]}
 v=g.verify(p,[{"status":"ok"},{"status":"denied"}])
 assert not v.ok and v.denied==1
 v=g.verify(p,[{"status":"ok"},{"status":"ok"}])
 assert v.ok and v.completed==2
