from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

@dataclass(frozen=True)
class CapabilityRule:
    name: str
    paths: tuple[str, ...]
    keywords: tuple[str, ...]
    priority: str

RULES=(
    CapabilityRule("terminal_agent",("alice/terminal/windows.py","alice/terminal"),("terminal","command","shell"),"high"),
    CapabilityRule("session_management",("alice/conversation/persistent.py","alice/conversation"),("session","conversation","history"),"high"),
    CapabilityRule("tool_orchestration",("alice/tools/registry.py","alice/orchestration/engine.py","alice/orchestration"),("tool","orchestration","mcp"),"high"),
    CapabilityRule("model_provider_abstraction",("alice/providers/router.py","alice/providers"),("provider","router","streaming"),"very_high"),
    CapabilityRule("workspace_intelligence",("alice/workspace/files.py","alice/workspace","alice/knowledge"),("workspace","project","filesystem"),"high"),
    CapabilityRule("streaming",("alice/providers/router.py","alice/ui/app.py","alice/core/completion.py"),("stream","streaming","chunk"),"medium"),
    CapabilityRule("agent_planning",("alice/agent/planner.py","alice/planning/planner.py","alice/planning"),("planner","plan","agent"),"medium"),
    CapabilityRule("testing_harness",("alice/tests","alice/maintenance/self_manager.py"),("pytest","test","compileall"),"high"),
)

def _existing_text(root:Path,paths:Iterable[str],limit=120000):
    chunks=[]; used=0
    for raw in paths:
        p=root/raw
        if p.is_file():
            try:text=p.read_text(encoding="utf-8",errors="replace")[:40000]
            except Exception:continue
            chunks.append(text); used+=len(text)
        elif p.is_dir():
            for q in sorted(p.rglob("*.py"))[:30]:
                try:text=q.read_text(encoding="utf-8",errors="replace")[:8000]
                except Exception:continue
                chunks.append(text); used+=len(text)
                if used>=limit:return "\n".join(chunks)[:limit]
        if used>=limit:break
    return "\n".join(chunks)[:limit]

def assess_capabilities(root,candidates,source_analysis=None):
    root=Path(root).resolve(); rows=[]
    for candidate in candidates or []:
        name=str(candidate.get("name","")).strip(); rule=next((r for r in RULES if r.name==name),None)
        if rule is None:
            rows.append({"name":name,"status":"unknown","alice_match":False,"recommendation":"manual_review","priority":"medium","reason":"No deterministic ALICE mapping exists yet."}); continue
        matched=[p for p in rule.paths if (root/p).exists()]; blob=_existing_text(root,rule.paths).lower(); hits=sum(1 for k in rule.keywords if k in blob)
        if matched and hits>=max(1,len(rule.keywords)//2): status="exists"; recommendation="compare_and_improve_only_if_source_is_better"
        elif matched: status="partial"; recommendation="improve_native_capability"
        else: status="missing"; recommendation="reimplement_natively"
        reason="ALICE already has a matching subsystem; do not duplicate it." if status=="exists" else "ALICE has part of this capability and should improve it selectively." if status=="partial" else "No matching ALICE subsystem was found; a native implementation may be justified."
        rows.append({"name":name,"status":status,"alice_match":bool(matched),"matched_paths":matched,"keyword_hits":hits,"priority":rule.priority,"recommendation":recommendation,"reason":reason})
    return {"version":2,"capabilities":rows,"recommended_for_native_review":[r["name"] for r in rows if r["status"] in {"missing","partial"}],"automatic_absorption":[],"policy":"comparison_only_until_explicit_reimplementation_approval"}
