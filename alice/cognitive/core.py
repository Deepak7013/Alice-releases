from __future__ import annotations
"""Local-first executive layer for ALICE.

This layer handles deterministic requests before an external model is needed,
coordinates durable memory, exposes capability/status summaries, and provides
safe intent classification. It does not grant itself permissions or execute
consequential actions without the existing runtime approval system.
"""
from dataclasses import dataclass
from decimal import Decimal, DivisionByZero, InvalidOperation, localcontext
import re
from typing import Any
from alice.reasoning.engine import ReasoningEngine
from .context import KnowledgeContextBuilder

@dataclass
class CoreDecision:
    handled: bool
    response: str = ""
    intent: str = "chat"
    needs_model: bool = True

class CognitiveCore:
    _ARITHMETIC = re.compile(
        r"^(?:what\s+is\s+)?(?P<left>\d{1,18}(?:\.\d{1,12})?)\s*"
        r"(?P<operator>[+*/x×-])\s*"
        r"(?P<right>\d{1,18}(?:\.\d{1,12})?)\s*[?!.]*$",
        re.IGNORECASE,
    )

    def __init__(self, memory=None, runtime=None, router=None, root=None, *, world_model=None):
        self.memory = memory
        self.runtime = runtime
        self.router = router
        self.root = root
        self.world_model = world_model
        self.context_builder = KnowledgeContextBuilder(world_model=world_model)
        self.reasoning = ReasoningEngine(router=router, memory=memory, root=root)

    def _planning_context(self, request):
        try:
            knowledge = self.context_builder.build(request, world_context=True)
            world = knowledge.world
            if not isinstance(world, dict) or not world.get("context"):
                return {}
            return {
                "world_model": {
                    "context": str(world["context"])[:8000],
                    "trust": "observation_only",
                    "sources": list(knowledge.sources),
                }
            }
        except Exception:
            return {}

    def classify(self, text: str) -> str:
        s = " ".join(str(text).lower().split())
        if self._ARITHMETIC.fullmatch(s):
            return "arithmetic"
        if any(x in s for x in ("what do you remember", "show my memories", "what do you know about alice")):
            return "memory_query"
        if s in {"status", "alice status", "system status", "are you awake", "are you online"}:
            return "status"
        if any(x in s for x in ("what can you do", "your capabilities", "capabilities", "what are your features")):
            return "capabilities"
        if any(x in s for x in ("health check", "self diagnostic", "diagnostics", "diagnose yourself")):
            return "diagnostics"
        if any(x in s for x in ("forget this", "forget that", "forget memory", "delete this memory")):
            return "memory_control"
        if s.startswith("correct memory") or s.startswith("update memory"):
            return "memory_correction"
        if s.startswith("plan ") or s in {"make a plan", "create a plan"}:
            return "planning"
        return "chat"

    @classmethod
    def _arithmetic_answer(cls, text: str) -> str | None:
        match = cls._ARITHMETIC.fullmatch(" ".join(str(text).strip().split()))
        if not match:
            return None
        try:
            left = Decimal(match.group("left"))
            right = Decimal(match.group("right"))
            operator = match.group("operator").casefold()
            with localcontext() as context:
                context.prec = 36
                if operator == "+":
                    result = left + right
                elif operator == "-":
                    result = left - right
                elif operator in {"x", "×", "*"}:
                    result = left * right
                elif right == 0:
                    return "Division by zero is undefined."
                else:
                    result = left / right
            rendered = format(result, "f")
            if "." in rendered:
                rendered = rendered.rstrip("0").rstrip(".")
            return rendered or "0"
        except (InvalidOperation, DivisionByZero, ValueError):
            return None

    def _status(self) -> str:
        providers = {}
        if self.router is not None and hasattr(self.router, "available"):
            try: providers = self.router.available()
            except Exception: providers = {}
        active = [k for k,v in providers.items() if v]
        memory = "available" if self.memory is not None else "unavailable"
        return "ALICE is online. Local memory: %s. Available AI providers: %s." % (memory, ", ".join(active) if active else "none")

    def _capabilities(self) -> str:
        return ("ALICE core capabilities: persistent conversation and local learning; memory retrieval; "
                "multi-step planning; verified tool execution; browser and desktop control; Android/ADB "
                "integration; voice/TTS; file and Office artifact creation; research; multi-agent workers; "
                "scheduled tasks; approvals/audit; self-diagnostics; protected in-place upgrades; and "
                "project/workspace management. External integrations remain unavailable until configured.")

    def _diagnostics(self) -> str:
        checks=[]
        try:
            checks.append("memory=OK" if self.memory is not None else "memory=MISSING")
            if self.runtime is not None:
                checks.append("runtime=OK")
                checks.append("scheduler=OK" if getattr(self.runtime, "scheduler", None) else "scheduler=MISSING")
                checks.append("approvals=OK" if getattr(self.runtime, "approvals", None) else "approvals=MISSING")
            else:
                checks.append("runtime=MISSING")
            if self.router is not None and hasattr(self.router, "available"):
                checks.append("provider_config=OK")
        except Exception as exc:
            checks.append("diagnostic_error=" + str(exc)[:120])
        return "ALICE self-diagnostic: " + ", ".join(checks) + "."

    def decide(self, text: str) -> CoreDecision:
        intent = self.classify(text)
        if intent == "arithmetic":
            answer = self._arithmetic_answer(text)
            if answer is not None:
                return CoreDecision(True, answer, intent, False)
        if intent == "memory_query" and self.memory is not None:
            answer = self.memory.local_memory_answer(text)
            return CoreDecision(True, answer or "I don't have any durable memories yet.", intent, False)
        if intent == "status":
            return CoreDecision(True, self._status(), intent, False)
        if intent == "capabilities":
            return CoreDecision(True, self._capabilities(), intent, False)
        if intent == "diagnostics":
            return CoreDecision(True, self._diagnostics(), intent, False)
        if intent == "memory_control":
            q=re.sub(r"(?i)^(forget this|forget that|forget memory|delete this memory)[:\s-]*", "", text.strip()).strip()
            if q and self.memory is not None:
                result=self.memory.forget(q,limit=10)
                if result.get("forgotten"):
                    return CoreDecision(True, f"Forgot {result['forgotten']} matching durable memory record(s).", intent, False)
                if result.get("reason") in {"ambiguous", "ambiguous_id"}:
                    choices=result.get("matches",[])
                    listing="\n".join(
                        f"- {str(row.get('id',''))[:8]} — [{row.get('kind','fact')}] "
                        f"{str(row.get('key',''))[:120]}: {str(row.get('value',''))[:180]}"
                        for row in choices if isinstance(row,dict)
                    )
                    return CoreDecision(True,"Several memories match; nothing was deleted. Choose one ID:\n"+listing,intent,False)
            return CoreDecision(True, "Tell me the specific memory or phrase to forget.", intent, False)
        if intent == "memory_correction":
            payload=re.sub(r"(?i)^(correct|update) memory[:\s-]*", "", text.strip()).strip()
            if "=>" in payload and self.memory is not None:
                old,new=[x.strip() for x in payload.split("=>",1)]
                result=self.memory.correct(old,new)
                if result.get("matches"):
                    choices=result.get("matches",[])
                    listing="\n".join(
                        f"- {str(row.get('id',''))[:8]} — [{row.get('kind','fact')}] "
                        f"{str(row.get('key',''))[:120]}: {str(row.get('value',''))[:180]}"
                        for row in choices if isinstance(row,dict)
                    )
                    return CoreDecision(True,"Several memories match; none was changed. Choose one ID, then use `correct memory <ID> => <new value>`:\n"+listing,intent,False)
                return CoreDecision(True, "Memory corrected." if result.get("ok") else result.get("reason","Memory correction failed."), intent, False)
            return CoreDecision(True, "Use: correct memory <old memory> => <new value>.", intent, False)
        if intent == "planning":
            goal=re.sub(r"(?i)^plan\s*", "", text.strip()).strip()
            try:
                grounded_context=self._planning_context(goal or text)
                plan=self.reasoning.plan(goal or text, context=grounded_context or None)
                lines=[f"Plan {plan.plan_id} ({plan.status.value}):"]
                lines += [f"{i}. {step.action} [risk={step.consequence}{", approval required" if step.requires_approval else ""}]" for i,step in enumerate(plan.steps,1)]
                if grounded_context:
                    lines.append("Grounding: bounded WorldModel observations attached as untrusted state data; refresh before consequential actions.")
                return CoreDecision(True,"\n".join(lines),intent,False)
            except Exception as exc:
                return CoreDecision(True,"Planning failed safely: "+str(exc)[:200],intent,False)
        return CoreDecision(False, "", intent, True)
