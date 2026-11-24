from __future__ import annotations
"""Unified executive-control contracts for ALICE's final architecture.

This module is deliberately policy-first and side-effect free.  It provides one
stable decision/context contract that higher layers can use without allowing a
normal conversation or hypothetical analysis to leak into an execution path.
Actual execution remains owned by the existing Runtime/Action/approval stack.
"""
from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any


class TaskIntent(str, Enum):
    CONVERSATION = "conversation"
    HYPOTHETICAL = "hypothetical"
    MEMORY = "memory"
    PLANNING = "planning"
    ACTION = "action"
    SELF_ENGINEERING = "self_engineering"
    DEVOUR = "devour"
    UPDATE = "update"
    DIAGNOSTIC = "diagnostic"


@dataclass
class ExecutiveContext:
    request: str
    intent: TaskIntent
    constraints: list[str] = field(default_factory=list)
    memory_context: str = ""
    plan: Any = None
    observations: list[Any] = field(default_factory=list)
    verification: Any = None
    lessons: list[str] = field(default_factory=list)
    approval_required: bool = False
    approval_reason: str = ""


class ExecutiveController:
    """Classify, contextualize and gate a task before downstream execution."""

    _HYPOTHETICAL = (
        "suppose", "hypothetically", "hypothetical", "imagine", "what if",
        "if a repository", "if a script", "would you", "what would you do",
        "explain what you would", "do not execute", "don't execute", "analysis only",
        "for analysis", "in theory",
    )
    _DEVOUR = ("devour", "assimilate", "ingest", "study this repository", "absorb")
    _SELF_ENGINEER = (
        "upgrade yourself", "upgrade alice", "self engineer", "self-engineer",
        "rewrite yourself", "modify your source", "fix your source",
    )
    _UPDATE = ("update yourself", "install this upgrade", "apply this upgrade")
    _PLAN = ("plan ", "make a plan", "create a plan", "how should we build")
    _MEMORY = ("remember", "what do you remember", "what do you know about")
    _DIAGNOSTIC = ("diagnose", "diagnostic", "health check", "self diagnostic", "status")
    _ACTION = (
        "open ", "close ", "launch ", "run ", "execute ", "create ", "delete ",
        "move ", "copy ", "install ", "send ", "download ", "click ", "type ",
        "build ", "generate ", "edit ", "write ", "modify ", "change ",
        "connect ", "check ", "inspect ", "look at ", "search ", "find ",
        "show ", "list ", "read ", "get ",
    )

    @staticmethod
    def _norm(text: str) -> str:
        return " ".join(str(text or "").strip().lower().split())

    def classify(self, request: str) -> TaskIntent:
        s = self._norm(request)
        if not s:
            return TaskIntent.CONVERSATION
        # Safety-critical precedence: hypothetical/analysis language wins before
        # action verbs.  A hypothetical mentioning "delete" is still analysis.
        if any(x in s for x in self._HYPOTHETICAL):
            return TaskIntent.HYPOTHETICAL
        if any(x in s for x in self._SELF_ENGINEER):
            return TaskIntent.SELF_ENGINEERING
        if any(x in s for x in self._DEVOUR):
            return TaskIntent.DEVOUR
        if any(x in s for x in self._UPDATE):
            return TaskIntent.UPDATE
        if any(x in s for x in self._DIAGNOSTIC):
            return TaskIntent.DIAGNOSTIC
        if re.match(r"^(?:what(?:'s| is) my battery|what(?:'s| is) the weather|"
                     r"check (?:my )?(?:battery|weather|system|status)|"
                     r"look at my screen|what do you see on my screen)\b",s):
            return TaskIntent.DIAGNOSTIC
        if any(x in s for x in self._MEMORY):
            return TaskIntent.MEMORY
        if any(x in s for x in self._PLAN) and not any(x in s for x in self._ACTION):
            return TaskIntent.PLANNING
        if any(s.startswith(x) for x in self._ACTION):
            return TaskIntent.ACTION
        return TaskIntent.CONVERSATION

    def prepare(self, request: str, *, memory_context: str = "", constraints: list[str] | None = None) -> ExecutiveContext:
        intent = self.classify(request)
        ctx = ExecutiveContext(
            request=str(request),
            intent=intent,
            memory_context=str(memory_context or ""),
            constraints=list(constraints or []),
        )
        if intent == TaskIntent.HYPOTHETICAL:
            ctx.constraints.extend(["analysis_only", "no_execution", "no_approval_prompt"])
        elif intent in {TaskIntent.ACTION, TaskIntent.SELF_ENGINEERING, TaskIntent.DEVOUR, TaskIntent.UPDATE}:
            ctx.approval_required = True
            ctx.approval_reason = "The requested operation may change files, devices, software, or protected state."
        return ctx

    @staticmethod
    def can_execute(ctx: ExecutiveContext) -> bool:
        return ctx.intent not in {TaskIntent.CONVERSATION, TaskIntent.HYPOTHETICAL, TaskIntent.MEMORY, TaskIntent.PLANNING, TaskIntent.DIAGNOSTIC}

    @staticmethod
    def requires_user_approval(ctx: ExecutiveContext) -> bool:
        return ctx.approval_required and "no_approval_prompt" not in ctx.constraints

    @staticmethod
    def completion_claim_is_safe(answer: str, verification: Any) -> bool:
        """Never certify a completion claim without positive verification evidence."""
        text = str(answer or "")
        if not re.search(r"(?i)\b(done|completed|successfully|finished)\b", text):
            return True
        if verification is None:
            return False
        if isinstance(verification, dict):
            return bool(verification.get("ok"))
        return bool(getattr(verification, "ok", False))
