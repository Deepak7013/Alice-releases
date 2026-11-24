from ..security.permissions import PermissionManager, Risk
from ..runtime.approval_context import is_ui_approved_action
import hashlib
import json
import math
import time
import uuid

class Executor:
    def __init__(self, tools, capabilities=None, postconditions=None, receipt_journal=None):
        self.tools=tools; self.permissions=PermissionManager(); self.capabilities=capabilities
        self.postconditions=postconditions if postconditions is not None else getattr(tools,"postconditions",None)
        self.receipt_journal = receipt_journal

    def _persist_receipt(self, item, *, admitted=False, execution_ok=False, verified=False, action_id=None):
        """Persist observed execution evidence when a journal is configured."""
        if self.receipt_journal is None:
            return
        from ..execution.execution_receipt import ExecutionReceiptFactory
        tool_name = item.get("tool")
        if not isinstance(tool_name, str) or not tool_name.strip():
            tool_name = "<invalid-plan>"
        # Persist a compact, privacy-conscious audit summary. Postcondition
        # evidence can contain file paths, page text, or other user data, so the
        # journal stores a digest rather than copying the raw observation.
        evidence_parts = []
        error = item.get("error")
        if isinstance(error, str) and error:
            evidence_parts.append(error[:512])
        error_class = item.get("error_class")
        if isinstance(error_class, str) and error_class:
            evidence_parts.append(f"error_class={error_class[:128]}")
        postcondition = item.get("postcondition")
        if isinstance(postcondition, dict):
            reason = postcondition.get("reason")
            if isinstance(reason, str) and reason:
                evidence_parts.append(f"postcondition={reason[:512]}")
            observed = postcondition.get("evidence")
            if observed is not None:
                try:
                    canonical = json.dumps(observed, sort_keys=True, separators=(",", ":"),
                                           ensure_ascii=False, default=str, allow_nan=False)
                    evidence_parts.append("postcondition_evidence_sha256=" +
                                          hashlib.sha256(canonical.encode("utf-8")).hexdigest())
                except (TypeError, ValueError):
                    evidence_parts.append("postcondition_evidence=unserializable")
        receipt = ExecutionReceiptFactory().create(
            action_id=action_id if action_id is not None else str(uuid.uuid4()),
            tool=tool_name, admitted=admitted, execution_ok=execution_ok,
            verified=verified, outcome=str(item.get("status", "unknown")),
            evidence="; ".join(evidence_parts)[:1000],
        )
        try:
            self.receipt_journal.append(receipt)
        except Exception as exc:
            # Do not conceal an action outcome if audit storage is unavailable.
            # Surface the degraded audit state on the corresponding step.
            item["receipt_persistence_error"] = f"{type(exc).__name__}: {exc}"
    def run(self, plan, *, cancel_event=None, timeout_seconds=None):
        """Execute a plan with cooperative cancellation and a between-step deadline.

        A deadline/cancel request prevents the next tool from starting. It does
        not forcibly interrupt a callable already running; tools that need hard
        interruption must implement their own cooperative cancellation or run
        in an isolated process.
        """
        started = time.monotonic()
        deadline = None
        if timeout_seconds is not None:
            if isinstance(timeout_seconds, bool):
                raise ValueError("timeout_seconds must be a positive finite number")
            try:
                budget = float(timeout_seconds)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("timeout_seconds must be a positive finite number") from exc
            if not math.isfinite(budget) or budget <= 0:
                raise ValueError("timeout_seconds must be a positive finite number")
            deadline = started + budget
        """Execute a validated sequence of tool steps without trusting planner shape.

        Planner output is model-generated input. Validate the outer envelope and
        each step before indexing fields or touching the registry so malformed
        output becomes a structured failure rather than an uncaught exception.
        """
        if not isinstance(plan, dict):
            return [{"step": 0, "tool": None, "status": "error",
                     "error": "Plan must be an object", "error_class": "PlanValidationError",
                     "effect_may_have_occurred": False}]
        steps = plan.get("steps")
        if not isinstance(steps, list):
            return [{"step": 0, "tool": None, "status": "error",
                     "error": "Plan steps must be a list", "error_class": "PlanValidationError",
                     "effect_may_have_occurred": False}]
        results=[]
        # Plans are ordered workflows: once a step is invalid, denied, or fails,
        # later steps must not run against an unknown/partially changed state.
        for index,step in enumerate(steps,1):
            if cancel_event is not None and cancel_event.is_set():
                results.append({"step": index, "tool": None, "status": "cancelled",
                                "error": "Execution cancelled before step started",
                                "error_class": "ExecutionCancelled", "effect_may_have_occurred": False})
                break
            if deadline is not None and time.monotonic() >= deadline:
                results.append({"step": index, "tool": None, "status": "timed_out",
                                "error": "Execution deadline reached before step started",
                                "error_class": "ExecutionDeadlineExceeded", "effect_may_have_occurred": False})
                break
            if not isinstance(step, dict):
                results.append({"step": index, "tool": None, "status": "error",
                                "error": "Plan step must be an object", "error_class": "PlanValidationError",
                                "effect_may_have_occurred": False})
                break
            name = step.get("tool")
            if not isinstance(name, str) or not name.strip():
                results.append({"step": index, "tool": name, "status": "error",
                                "error": "Plan step requires a non-empty tool name",
                                "error_class": "PlanValidationError", "effect_may_have_occurred": False})
                break
            args = step.get("args", {})
            if not isinstance(args, dict):
                results.append({"step": index, "tool": name, "status": "error",
                                "error": "Tool arguments must be an object",
                                "error_class": "PlanValidationError", "effect_may_have_occurred": False})
                break
            action_id = step.get("action_id")
            if action_id is not None and (not isinstance(action_id, str) or not action_id.strip()):
                invalid_id = {"step": index, "tool": name, "status": "error",
                              "error": "action_id must be a non-empty string",
                              "error_class": "PlanValidationError", "effect_may_have_occurred": False}
                results.append(invalid_id)
                break
            if action_id is not None and self.receipt_journal is not None:
                try:
                    already_recorded = any(row.get("action_id") == action_id
                                            for row in self.receipt_journal.list())
                    get_claim = getattr(self.receipt_journal, "get_action_claim", None)
                    already_claimed = bool(callable(get_claim) and get_claim(action_id))
                except Exception as exc:
                    blocked = {"step": index, "tool": name, "status": "error",
                               "error": f"Cannot establish action history: {exc}",
                               "error_class": "ReceiptJournalUnavailable",
                               "effect_may_have_occurred": False}
                    results.append(blocked)
                    break
                if already_recorded or already_claimed:
                    duplicate = {"step": index, "tool": name, "status": "duplicate_prevented",
                                 "error": "This action_id already has a persisted receipt or durable execution claim",
                                 "effect_may_have_occurred": False}
                    results.append(duplicate)
                    break
            tool=self.tools.get(name)
            if tool is None:
                results.append({'step':index,'tool':name,'status':'error','error':'Unknown tool',
                                'error_class':'UnknownToolError','effect_may_have_occurred':False}); break
            risk=Risk(tool.risk)
            # Safe workspace writes, ordinary desktop interactions and browsing can
            # proceed without a confirmation on every step. Consequential actions
            # and system/self-modification still require explicit approval.
            if self.permissions.needs_confirmation(name,args) and not is_ui_approved_action():
                if not self.permissions.request(f'Alice wants to use tool: {name}',f'Arguments: {args}'):
                    denied = {'step':index,'tool':name,'status':'denied','effect_may_have_occurred':False}
                    self._persist_receipt(denied, admitted=False, execution_ok=False, action_id=action_id)
                    results.append(denied); break
            # Approval can involve a human dialog and may take arbitrarily long.
            # Re-check lifecycle controls at the last safe boundary so an action
            # is not launched after cancellation/deadline while awaiting approval.
            if cancel_event is not None and cancel_event.is_set():
                results.append({"step": index, "tool": name, "status": "cancelled",
                                "error": "Execution cancelled before tool invocation",
                                "error_class": "ExecutionCancelled", "effect_may_have_occurred": False})
                break
            if deadline is not None and time.monotonic() >= deadline:
                results.append({"step": index, "tool": name, "status": "timed_out",
                                "error": "Execution deadline reached before tool invocation",
                                "error_class": "ExecutionDeadlineExceeded", "effect_may_have_occurred": False})
                break
            if action_id is not None and self.receipt_journal is not None:
                claim_action = getattr(self.receipt_journal, "claim_action", None)
                if callable(claim_action):
                    try:
                        if not claim_action(action_id, name):
                            results.append({"step": index, "tool": name, "status": "duplicate_prevented",
                                            "error": "This action_id was claimed by another execution",
                                            "effect_may_have_occurred": False})
                            break
                    except Exception as exc:
                        results.append({"step": index, "tool": name, "status": "error",
                                        "error": f"Cannot claim action safely: {exc}",
                                        "error_class": "ReceiptJournalUnavailable",
                                        "effect_may_have_occurred": False})
                        break
            try:
                run_registered = getattr(self.tools, "run_registered", None)
                if callable(run_registered):
                    remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
                    if remaining is not None and remaining <= 0:
                        results.append({"step": index, "tool": name, "status": "timed_out",
                                        "error": "Execution deadline reached before tool invocation",
                                        "error_class": "ExecutionDeadlineExceeded",
                                        "effect_may_have_occurred": False})
                        break
                    out = run_registered(tool, args, cancel_event=cancel_event,
                                          timeout_seconds=remaining)
                else:
                    out = self.tools.run(name, args)
                check=None
                if isinstance(out,dict) and out.get('status')=='denied':
                    status='denied'
                elif isinstance(out,dict) and out.get('status')=='not_sent':
                    status='not_sent'
                elif tool.risk=='read':
                    status='observed'
                else:
                    status='attempted'
                    if self.postconditions is not None and self.postconditions.has(name):
                        check=self.postconditions.verify(name,args,out)
                        if check.ok:
                            status='verified'
                            if self.capabilities is not None and self.capabilities.get(name) is not None:
                                canonical=json.dumps(check.evidence,sort_keys=True,separators=(",",":"),
                                                     ensure_ascii=False,default=str)
                                evidence_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                                success = {
                                    "note": check.reason or "Independent postcondition observed.",
                                    "evidence_sha256": evidence_sha256,
                                    "observer": name,
                                }
                                if callable(getattr(self.capabilities, "bind_runtime_callable", None)):
                                    success["runtime_callable"] = getattr(tool, "fn", None)
                                self.capabilities.record_success(name, **success)
                        elif self.capabilities is not None and self.capabilities.get(name) is not None:
                            self.capabilities.record_failure(name,check.reason or 'postcondition not observed',degraded=True)

                public_out=dict(out) if isinstance(out,dict) else out
                if isinstance(public_out,dict):
                    public_out.pop('_postcondition_context',None)
                    reported_status=public_out.get('status')
                    if reported_status and reported_status!=status:
                        public_out['tool_reported_status']=reported_status
                    reported_verified=public_out.pop('verified',None)
                    if reported_verified is not None:
                        public_out['tool_reported_verified']=bool(reported_verified)
                    public_out['status']=status
                    public_out['verified']=status=='verified'
                    if check is not None:
                        reported_evidence=public_out.pop('evidence',None)
                        if status=='verified':
                            public_out['evidence']=check.evidence
                        elif reported_evidence is not None:
                            public_out['tool_evidence_unverified']=reported_evidence
                        public_out['postcondition']={'ok':check.ok,'reason':check.reason,'evidence':check.evidence}
                step_result={
                    'step': index, 'tool': name, 'status': status,
                    'verified': status == 'verified', 'result': public_out,
                    'declared_tool_timeout_seconds': tool.timeout_seconds,
                    'timeout_enforcement': ('cooperative_signal_only' if tool.cancellation_supported
                                            else 'not_enforced_for_in_process_callable'),
                    'cancellation_mode': 'cooperative_token' if tool.cancellation_supported else 'unsupported',
                }
                if cancel_event is not None and cancel_event.is_set():
                    # The callable has returned; do not relabel its outcome as
                    # cancelled because its side effects may already have occurred.
                    step_result['cancellation_requested_during_call'] = True
                if check is not None:
                    step_result['postcondition']={'ok':check.ok,'reason':check.reason,'evidence':check.evidence}
                self._persist_receipt(step_result, admitted=True,
                                      execution_ok=status in {"observed", "attempted", "verified"},
                                      verified=status == "verified", action_id=action_id)
                results.append(step_result)
                if status in {'denied', 'not_sent'}:
                    break
                if check is not None and not check.ok:
                    # A failed postcondition means the requested state change was
                    # not independently observed; do not continue dependent work.
                    break
            except Exception as exc:
                if self.capabilities is not None and self.capabilities.get(name) is not None:
                    self.capabilities.record_failure(name,exc,degraded=True)
                failed = {'step':index,'tool':name,'status':'error','error':str(exc),
                          'error_class':type(exc).__name__,'risk':str(tool.risk),
                          'effect_may_have_occurred':tool.risk!='read'}
                self._persist_receipt(failed, admitted=True, execution_ok=False, action_id=action_id)
                results.append(failed)
                break
        elapsed = max(0.0, time.monotonic() - started)
        for item in results:
            item.setdefault("execution_elapsed_seconds", round(elapsed, 6))
        return results
