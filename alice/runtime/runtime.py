"""Durable runtime primitives for Alice: events, approvals, audit and schedules."""
from __future__ import annotations
import hashlib, json, threading, time, uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from .approval_context import ui_approved_action
from .outcomes import is_verified_action_outcome
from typing import Callable, Any


def _now():
    return datetime.now(timezone.utc).isoformat()

class AuditLog:
    def __init__(self, root=None):
        self.path=Path(root or Path(__file__).resolve().parents[2]) / "alice_workspace" / "runtime" / "audit.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock=threading.Lock()
    def record(self, event, **data):
        row={"id":uuid.uuid4().hex[:12],"time":_now(),"event":event,"data":data}
        with self._lock:
            with self.path.open("a",encoding="utf-8") as f: f.write(json.dumps(row,ensure_ascii=False,default=str)+"\n")
        return row
    def recent(self, limit=50):
        if not self.path.exists(): return []
        lines=self.path.read_text(encoding="utf-8").splitlines()[-limit:]
        return [json.loads(x) for x in lines if x.strip()]

class EventBus:
    def __init__(self, audit=None):
        self.audit=audit or AuditLog(); self.handlers={}; self._lock=threading.RLock()
    def subscribe(self,event,handler):
        with self._lock: self.handlers.setdefault(event,[]).append(handler)
    def publish(self,event,payload=None):
        payload=payload or {}; self.audit.record("event",name=event,payload=payload)
        with self._lock: handlers=list(self.handlers.get(event,[]))+list(self.handlers.get("*",[]))
        results=[]
        for h in handlers:
            try: results.append(h(payload))
            except Exception as e: self.audit.record("event_handler_error",name=event,error=str(e))
        return results

@dataclass
class Approval:
    id:str
    action:str
    reason:str
    status:str="pending"
    created:str=""
    resolved:str=""

class ApprovalManager:
    def __init__(self, root=None, audit=None):
        self.root=Path(root or Path(__file__).resolve().parents[2]); self.path=self.root/"alice_workspace"/"runtime"/"approvals.json"; self.path.parent.mkdir(parents=True,exist_ok=True)
        self.audit=audit or AuditLog(self.root); self._lock=threading.Lock(); self.data=self._load()
    def _load(self):
        try:return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:return {}
    def _save(self): self.path.write_text(json.dumps(self.data,indent=2,ensure_ascii=False),encoding="utf-8")
    def request(self,action,reason):
        a=Approval(uuid.uuid4().hex[:10],action,reason,created=_now());
        with self._lock: self.data[a.id]=asdict(a); self._save()
        self.audit.record("approval_requested",approval_id=a.id,action=action,reason=reason); return asdict(a)
    def resolve(self,approval_id,approved):
        with self._lock:
            if approval_id not in self.data: raise KeyError(approval_id)
            self.data[approval_id]["status"]="approved" if approved else "denied"; self.data[approval_id]["resolved"]=_now(); self._save()
            result=dict(self.data[approval_id])
        self.audit.record("approval_resolved",approval_id=approval_id,status=result["status"]); return result
    def pending(self): return [v for v in self.data.values() if v.get("status")=="pending"]

@dataclass
class ScheduledJob:
    id:str
    name:str
    interval_seconds:int
    request:str
    enabled:bool=True
    next_run:float=0.0
    last_run:float=0.0

class Scheduler:
    """Persistent interval scheduler. One process owns execution; jobs are bounded by the callback."""
    def __init__(self, root=None, audit=None):
        self.root=Path(root or Path(__file__).resolve().parents[2]); self.path=self.root/"alice_workspace"/"runtime"/"schedule.json"; self.path.parent.mkdir(parents=True,exist_ok=True)
        self.audit=audit or AuditLog(self.root); self.jobs=self._load(); self._callbacks={}; self._thread=None; self._stop=threading.Event(); self._lock=threading.RLock()
    def _load(self):
        try:return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:return {}
    def _save(self): self.path.write_text(json.dumps(self.jobs,indent=2,ensure_ascii=False),encoding="utf-8")
    def add(self,name,interval_seconds,request):
        if int(interval_seconds)<60: raise ValueError("Minimum scheduler interval is 60 seconds")
        j=ScheduledJob(uuid.uuid4().hex[:10],name,int(interval_seconds),request,True,time.time()+int(interval_seconds));
        with self._lock:self.jobs[j.id]=asdict(j);self._save()
        self.audit.record("schedule_added",job=self.jobs[j.id]); return self.jobs[j.id]
    def remove(self,job_id):
        with self._lock:
            if job_id not in self.jobs:return False
            self.jobs.pop(job_id);self._save()
        self.audit.record("schedule_removed",job_id=job_id);return True
    def enable(self,job_id,enabled=True):
        with self._lock:
            if job_id not in self.jobs:raise KeyError(job_id)
            self.jobs[job_id]["enabled"]=bool(enabled);self._save()
        return self.jobs[job_id]
    def list(self): return list(self.jobs.values())
    def start(self,callback:Callable[[str],Any]):
        if self._thread and self._thread.is_alive(): return
        self._callbacks["run"]=callback; self._stop.clear(); self._thread=threading.Thread(target=self._loop,daemon=True);self._thread.start()
    def stop(self): self._stop.set()
    def _loop(self):
        while not self._stop.wait(2):
            now=time.time(); due=[]
            with self._lock:
                for j in self.jobs.values():
                    if j.get("enabled") and now>=j.get("next_run",0):
                        j["next_run"]=now+j["interval_seconds"];j["last_run"]=now;due.append(dict(j))
                if due:self._save()
            for j in due:
                self.audit.record("schedule_triggered",job_id=j["id"],name=j["name"])
                try:self._callbacks["run"](j["request"])
                except Exception as e:self.audit.record("schedule_error",job_id=j["id"],error=str(e))

class AliceRuntime:
    def __init__(self, root=None, agent=None, agency=None, world=None):
        self.root=Path(root or Path(__file__).resolve().parents[2]); self.audit=AuditLog(self.root); self.events=EventBus(self.audit); self.approvals=ApprovalManager(self.root,self.audit); self.scheduler=Scheduler(self.root,self.audit); self.agent=agent; self.world=world
        if agency is None:
            try:
                from ..agency import AgencyEngine
                self.agency=AgencyEngine(self.root, runtime=self)
            except Exception:
                self.agency=None
        else:
            self.agency=agency
    def _observe_world_outcome(self,payload):
        """Persist a bounded, provenance-labelled runtime outcome in shared world state."""
        if self.world is None: return
        try:
            evidence=payload.get("verification_evidence")
            canonical=json.dumps(evidence,sort_keys=True,separators=(",",":"),ensure_ascii=False,default=str)
            request_hash=hashlib.sha256(str(payload.get("request","")).encode("utf-8")).hexdigest()
            evidence_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest() if evidence is not None else None
            raw_tools=payload.get("tool_sequence",[])
            if not isinstance(raw_tools,list): raw_tools=[]
            tools=[str(name)[:100] for name in raw_tools[:32] if str(name).strip()]
            record={"task_id":str(payload.get("task_id","")),
                    "completion_state":str(payload.get("completion_state","failed"))[:40],
                    "verified":payload.get("verified") is True,"tools":tools,
                    "request_sha256":request_hash,"verification_evidence_sha256":evidence_hash,
                    "observed_at":_now()}
            recovery=payload.get("recovery_evidence")
            if isinstance(recovery,dict) and recovery.get("observed") is True:
                recovery_json=json.dumps(recovery,sort_keys=True,separators=(",",":"),default=str)
                record["verified_recovery_evidence_sha256"]=hashlib.sha256(recovery_json.encode("utf-8")).hexdigest()
            diagnostics=payload.get("failure_diagnostics",[])
            if isinstance(diagnostics,list) and diagnostics:
                safe=[row for row in diagnostics[:16] if isinstance(row,dict)]
                canonical_diagnostics=json.dumps(safe,sort_keys=True,separators=(",",":"),default=str)
                record["failure_count"]=len(safe)
                record["failure_diagnostics_sha256"]=hashlib.sha256(canonical_diagnostics.encode("utf-8")).hexdigest()
            self.world.observe("tasks","latest_runtime_outcome",record,
                               source="alice_runtime.outcome_event",confidence=1.0,ttl_seconds=86400)
        except Exception as exc:
            try:self.audit.record("world_outcome_observation_failed",task_id=payload.get("task_id"),error=str(exc)[:300])
            except Exception:pass

    def submit(self,request,source="user",require_approval=False,reason="",direct_tool=None,direct_args=None):
        task_id=uuid.uuid4().hex
        self.audit.record("task_submitted",task_id=task_id,request=request,source=source)
        policy_needs=False
        if self.agent is not None and hasattr(self.agent,"policy"):
            try: policy_needs=bool(self.agent.policy.inspect_request(request).get("needs_confirmation"))
            except Exception: policy_needs=False
        if require_approval or (policy_needs and source != "approved-ui"):
            return {"status":"awaiting_approval","task_id":task_id,"approval":self.approvals.request(request,reason or "Consequential action requires user confirmation.")}
        if not self.agent:return {"status":"queued","task_id":task_id,"request":request}
        self.audit.record("task_started",task_id=task_id,request=request,source=source)
        try:
            run_with_outcome=getattr(self.agent,"run_with_outcome",None)
            run_direct=getattr(self.agent,"run_direct_tool_with_outcome",None)
            with ui_approved_action(source=="approved-ui"):
                if direct_tool is not None and callable(run_direct):
                    outcome=run_direct(request,direct_tool,direct_args or {})
                elif direct_tool is not None:
                    outcome={"summary":"This ALICE runtime doesn't support the requested direct action.","completion_state":"unverified","verified":False}
                elif callable(run_with_outcome):
                    outcome=run_with_outcome(request)
                else:
                    outcome={"summary":self.agent.run(request),"completion_state":"conversation","verified":False}
            if not isinstance(outcome,dict):
                outcome={"summary":str(outcome),"completion_state":"conversation","verified":False}
            result=str(outcome.get("summary", ""))
            evidence=outcome.get("verification_evidence")
            verified=is_verified_action_outcome(outcome)
            requested_state=str(outcome.get("completion_state","unverified"))
            state="verified" if verified else ("unverified" if requested_state=="verified" else requested_state)
            payload={"task_id":task_id,"request":request,"source":source,"verified":verified,
                     "completion_state":state,"verification_evidence":evidence if verified else None,
                     "tool_sequence":outcome.get("tool_sequence",[]),
                     "failure_diagnostics":outcome.get("failure_diagnostics",[]),
                     "recovery_evidence":outcome.get("recovery_evidence")}
            self.audit.record("task_returned",task_id=task_id,request=request,source=source,verified=verified,state=state)
            self._observe_world_outcome(payload)
            if verified:
                self.events.publish("task.completed",payload)
                if self.agency:self.agency.observe("task_completed",payload,source="runtime")
            elif state=="unverified":
                self.events.publish("task.failed",{**payload,"error":"action_outcome_unverified"})
                if self.agency:self.agency.observe("task_failed",payload,source="runtime")
            elif state=="observed":
                self.events.publish("task.observed",payload)
            else:
                self.events.publish("task.returned",payload)
            return {"status":"completed","task_id":task_id,"result":result,"verified":verified,
                    "completion_state":state,"verification_evidence":payload["verification_evidence"]}
        except Exception as e:
            failed={"task_id":task_id,"request":request,"source":source,"completion_state":"failed","verified":False,"tool_sequence":[]}
            self._observe_world_outcome(failed)
            self.audit.record("task_failed",task_id=task_id,request=request,error=str(e)); self.events.publish("task.failed",{**failed,"error":str(e)})
            if self.agency:
                self.agency.observe("task_failed", {"request":request,"source":source,"error":str(e)}, source="runtime")
            return {"status":"failed","error":str(e)}
    def start_scheduler(self): self.scheduler.start(lambda req:self.submit(req,source="scheduler"))
    def stop_scheduler(self): self.scheduler.stop()
