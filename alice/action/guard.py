from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass
class ActionVerification:
    ok: bool
    completed: int
    failed: int
    denied: int
    unknown: int
    message: str

class ActionGuard:
    """Preflight and postflight guard for tool actions.

    It never grants permissions. The existing PermissionManager remains the
    authority for confirmations; this layer only validates structure and
    verifies reported outcomes after execution.
    """
    def __init__(self, tools, permissions=None):
        self.tools=tools
        self.permissions=permissions

    def preflight(self, plan):
        errors=[]; preview=[]
        for i,step in enumerate(plan.get("steps",[]),1):
            name=step.get("tool",""); args=step.get("args") or {}
            tool=self.tools.get(name)
            if tool is None:
                errors.append(f"step {i}: unknown tool {name}"); continue
            if not isinstance(args,dict): errors.append(f"step {i}: args must be an object")
            preview.append({"step":i,"tool":name,"risk":tool.risk,"args":args,
                            "approval_required":bool(self.permissions and self.permissions.needs_confirmation(name,args))})
        return {"ok":not errors and bool(plan.get("steps")),"errors":errors,"preview":preview}

    def verify(self, plan, results):
        expected=len(plan.get("steps",[])); completed=failed=denied=unknown=0
        for r in results:
            status=r.get("status") if isinstance(r,dict) else None
            if status=="ok": completed+=1
            elif status=="denied": denied+=1
            elif status=="error": failed+=1
            else: unknown+=1
        ok=expected>0 and completed==expected
        if ok: msg="All planned actions reported success."
        elif failed: msg="One or more actions failed; do not claim completion."
        elif denied: msg="One or more actions were denied; do not claim completion."
        else: msg="Action results were incomplete or unrecognized."
        return ActionVerification(ok,completed,failed,denied,unknown,msg)
