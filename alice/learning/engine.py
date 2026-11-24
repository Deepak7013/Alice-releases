"""Evidence-driven learning engine for ALICE.

Turns verified task outcomes into bounded reusable lessons.  Learning can
recommend better workflows, but it never grants authority, executes actions,
or edits protected source code.
"""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import hashlib, json, re, time
from collections import Counter, defaultdict

from ..experience.global_store import GlobalExperienceStore
from ..core.atomic_json import atomic_write_json

_SECRET = re.compile(r"(?i)(api[_-]?key|token|password|secret|authorization|credential)")
_SPACE = re.compile(r"\s+")
_DIGITS = re.compile(r"\b\d+\b")


class LearningEngine:
    VERSION = "v3.17.0"
    # Closed set emitted by AliceAgent._task_outcome and its bounded recovery path.
    # Unknown codes may still be retained as bounded diagnostics, but cannot seed
    # regression/evaluation cases.
    TRUSTED_RUNTIME_FAILURE_CODES = frozenset({
        "malformed_result", "invalid_verification_evidence",
        "postcondition_unavailable", "postcondition_not_observed",
        "postcondition_failed", "tool_error", "tool_timeout", "target_stale",
        "action_denied", "delivery_not_sent", "recovery_mutation_blocked",
        "unverified_result", "read_observation_failed",
    })

    def __init__(self, root=None, max_records=1500):
        self.root = Path(root or Path(__file__).resolve().parents[2])
        self.store = GlobalExperienceStore(self.root, max_records=max_records)
        self.path = self.root / "alice_workspace" / "learning_engine.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("invalid learning state")
            data.setdefault("lessons", [])
            data.setdefault("regressions", [])
            data.setdefault("eval_cases", [])
            data.setdefault("recoveries", [])
            return data
        except Exception:
            return {"lessons": [], "regressions": [], "eval_cases": [], "recoveries": []}

    def _save(self):
        atomic_write_json(self.path, self.data)

    @staticmethod
    def _norm(text):
        text = str(text or "").lower()
        text = _SECRET.sub("<secret>", text)
        text = _DIGITS.sub("<n>", text)
        return _SPACE.sub(" ", text).strip()[:1000]

    @classmethod
    def failure_fingerprint(cls, error=None, error_class=None):
        basis = cls._norm(f"{error_class or ''}|{error or ''}")
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16] if basis.strip("|") else ""

    def record(self, task, workflow, success, *, duration_ms=0, error=None,
               error_class=None, evidence=None, tools=None, context=None,
               verified=False, quality=0.0):
        """Record one outcome and update the lesson/regression index."""
        success = bool(success)
        evidence = dict(evidence or {})
        evidence["verified"] = bool(evidence.get("verified", verified))
        evidence["quality"] = max(0.0, min(1.0, float(evidence.get("quality", quality) or 0)))
        if error_class:
            evidence["error_class"] = str(error_class)[:120]
        fp = self.failure_fingerprint(error, error_class)
        if fp:
            evidence["failure_fingerprint"] = fp
        rec = self.store.record(task, workflow, success, duration_ms=duration_ms,
                                evidence=evidence, tools=tools, context=context)
        lesson = self._update_lesson(str(task), str(workflow), success, fp, error, evidence)
        self._save()
        return {"recorded": True, "success": success, "workflow": workflow,
                "lesson": lesson, "experience": asdict(rec)}

    def record_verified_runtime_outcome(self, payload):
        """Persist a positive runtime lesson only from observed mutation evidence."""
        from ..runtime.outcomes import is_verified_action_outcome
        if not is_verified_action_outcome({
            "verified":payload.get("verified") if isinstance(payload,dict) else None,
            "verification_evidence":payload.get("verification_evidence") if isinstance(payload,dict) else None,
        }):
            return {"recorded":False,"reason":"independent_verified_action_evidence_required"}
        request=str(payload.get("request","")).strip()
        if not request:
            return {"recorded":False,"reason":"request_required"}
        source=str(payload.get("source","runtime"))[:80]
        tools=payload.get("tool_sequence",[])
        if not isinstance(tools,list): tools=[]
        evidence=payload["verification_evidence"]
        return self.record(request,f"runtime:{source}",True,verified=True,quality=0.9,
                           tools=tools,evidence=evidence,
                           context={"source":source,"completion_state":"verified"})

    def record_runtime_action_failures(self, payload):
        """Persist bounded, hash-only diagnostics for unverified tool outcomes."""
        if not isinstance(payload, dict):
            return {"recorded":False,"count":0}
        rows=payload.get("failure_diagnostics",[])
        if not isinstance(rows,list):
            return {"recorded":False,"count":0}
        accepted=0; regression_seeds_created=0; regression_cases_graded=0
        seen_regression_events=set()
        for row in rows[:16]:
            if not isinstance(row,dict):
                continue
            tool=str(row.get("tool", ""))[:100]
            code=str(row.get("failure_code", ""))[:80]
            if not re.fullmatch(r"[A-Za-z0-9_.:-]+",tool) or not re.fullmatch(r"[A-Za-z0-9_.:-]+",code):
                continue
            hashes={key:row[key] for key in ("detail_sha256","evidence_sha256")
                    if isinstance(row.get(key),str) and re.fullmatch(r"[0-9a-f]{64}",row[key])}
            evidence={"verified":False,"quality":0.0,"failure_code":code,**hashes}
            outcome=self.record("runtime action outcome",f"runtime_action_failure:{tool}:{code}",False,
                error=f"{tool}:{code}",error_class="ActionPostconditionFailure",
                evidence=evidence,tools=[tool],
                context={"source":str(payload.get("source","runtime"))[:80],
                         "completion_state":str(payload.get("completion_state","unverified"))[:40]})
            accepted+=1
            signature=(tool,code)
            if code not in self.TRUSTED_RUNTIME_FAILURE_CODES or signature in seen_regression_events:
                continue
            seen_regression_events.add(signature)
            # A recovered read failure may accompany a verified completed task.
            # It must not create or grade the generic "remain unverified" case.
            if (code=="read_observation_failed" and payload.get("verified") is True
                    and payload.get("completion_state")=="verified"
                    and isinstance(payload.get("recovery_evidence"),dict)):
                continue
            fp=self.failure_fingerprint(f"{tool}:{code}","ActionPostconditionFailure")
            occurrences=int(outcome.get("lesson",{}).get("failure_fingerprints",{}).get(fp,0))
            case_name=self._runtime_failure_regression_case_name(code)
            case_existed=any(isinstance(case,dict) and case.get("name")==case_name
                             for case in self.data.get("eval_cases",[]))
            fail_closed=(payload.get("verified") is False
                         and payload.get("completion_state")=="unverified"
                         and payload.get("verification_evidence") is None)
            if not fail_closed:
                if case_existed:
                    self.grade_eval(case_name,success=False,score=0.0,
                        notes="runtime fail-closed envelope did not match")
                    regression_cases_graded+=1
                continue
            if occurrences>=2:
                if self._record_runtime_failure_regression(code,occurrences):
                    regression_seeds_created+=1
                elif case_existed:
                    self.grade_eval(case_name,success=True,score=1.0,
                        notes="runtime fail-closed envelope matched")
                    regression_cases_graded+=1
        return {"recorded":accepted>0,"count":accepted,
                "regression_seeds_created":regression_seeds_created,
                "regression_cases_graded":regression_cases_graded}

    @staticmethod
    def _runtime_failure_regression_case_name(failure_code):
        from .regression_seed import RegressionSeedGenerator
        scenario=f"runtime action failure code recurred: {failure_code}"
        expected="action remains unverified and no positive completion is recorded"
        reason=f"trusted runtime failure-code recurrence: {failure_code}"
        seed=RegressionSeedGenerator().create(
            scenario=scenario,expected=expected,reason=reason,verified_failure=True)
        if not seed.get("created"):
            return ""
        return f"runtime-failure-{failure_code}-{seed['seed']['fingerprint']}"

    def _record_runtime_failure_regression(self, failure_code, occurrences):
        """Create a non-executable eval case after a trusted failure recurs."""
        from .regression_seed import RegressionSeedGenerator
        scenario=f"runtime action failure code recurred: {failure_code}"
        expected="action remains unverified and no positive completion is recorded"
        reason=f"trusted runtime failure-code recurrence: {failure_code}"
        result=RegressionSeedGenerator().create(
            scenario=scenario,expected=expected,reason=reason,verified_failure=True)
        if not result.get("created"):
            return False
        seed=result["seed"]
        regressions=self.data.setdefault("regressions",[])
        existing=next((row for row in regressions if isinstance(row,dict)
                       and row.get("fingerprint")==seed["fingerprint"]),None)
        created=existing is None
        if existing is None:
            existing={**seed,"failure_code":failure_code,"occurrences":int(occurrences),
                      "source":"trusted_runtime_failure_recurrence","created_at":time.time()}
            regressions.append(existing)
            self.data["regressions"]=regressions[-500:]
        else:
            existing["occurrences"]=max(int(existing.get("occurrences",0)),int(occurrences))
            existing["updated_at"]=time.time()
        case_name=self._runtime_failure_regression_case_name(failure_code)
        if not any(isinstance(case,dict) and case.get("name")==case_name
                   for case in self.data.get("eval_cases",[])):
            self.register_eval_case(case_name,scenario,expected=expected,
                tags=["runtime_failure","trusted_failure_code:"+failure_code,
                      "regression_seed:"+seed["fingerprint"]])
        else:
            self._save()
        return created

    def record_verified_recovery_outcome(self, payload):
        """Link a fresh observation and changed plan to a verified recovery result."""
        from ..runtime.outcomes import is_verified_action_outcome
        if not isinstance(payload,dict) or not is_verified_action_outcome(payload):
            return {"recorded":False,"reason":"independently_verified_action_required"}
        evidence=payload.get("recovery_evidence")
        if not isinstance(evidence,dict) or evidence.get("observed") is not True:
            return {"recorded":False,"reason":"fresh_observation_recovery_evidence_required"}
        code=str(evidence.get("failure_code",""))
        observer=str(evidence.get("observer_tool",""))
        digests={key:evidence.get(key) for key in
                 ("observation_sha256","recovery_plan_sha256","verified_action_evidence_sha256")}
        if (code!="read_observation_failed" or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}",observer)
                or any(not isinstance(value,str) or not re.fullmatch(r"[0-9a-f]{64}",value)
                       for value in digests.values())):
            return {"recorded":False,"reason":"recovery_evidence_invalid"}
        request_hash=hashlib.sha256(str(payload.get("request","")).encode("utf-8")).hexdigest()
        canonical=json.dumps({"request_sha256":request_hash,"observer_tool":observer,
                              "failure_code":code,**digests},sort_keys=True,separators=(",",":"))
        row={"recovery_id":hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
             "request_sha256":request_hash,"observer_tool":observer,"failure_code":code,
             **digests,"verified":True,"recorded_at":time.time()}
        rows=self.data.setdefault("recoveries",[])
        if not isinstance(rows,list):
            rows=[]
            self.data["recoveries"]=rows
        prior_recovery_ids={
            old.get("recovery_id") for old in rows
            if isinstance(old,dict)
            and old.get("verified") is True
            and old.get("failure_code")==code
            and old.get("observer_tool")==observer
            and isinstance(old.get("recovery_id"),str)
            and re.fullmatch(r"[0-9a-f]{64}",old["recovery_id"])
            and all(isinstance(old.get(key),str) and re.fullmatch(r"[0-9a-f]{64}",old[key])
                    for key in ("observation_sha256","recovery_plan_sha256",
                                "verified_action_evidence_sha256"))
        }
        is_new=row["recovery_id"] not in {
            old.get("recovery_id") for old in rows if isinstance(old,dict)
        }
        if is_new:
            rows.append(row)
            self.data["recoveries"]=rows[-500:]
        case_name,scenario,expected=self._verified_recovery_eval_identity(observer)
        case_exists=any(isinstance(case,dict) and case.get("name")==case_name
                        for case in self.data.get("eval_cases",[]))
        if not case_exists:
            self.register_eval_case(case_name,scenario,expected=expected,
                tags=["verified_recovery","failure_code:"+code,"observer:"+observer])
        elif is_new and prior_recovery_ids:
            self.grade_eval(case_name,success=True,score=1.0,
                notes="independent recovery evidence and postcondition passed")
        elif is_new:
            self._save()
        return {"recorded":True,"recovery_id":row["recovery_id"]}

    @staticmethod
    def _verified_recovery_eval_identity(observer_tool):
        scenario=f"bounded recovery after read_observation_failed observed by {observer_tool}"
        expected="fresh observation, changed plan, and independently verified mutation are linked"
        fingerprint=hashlib.sha256((scenario+"\n"+expected).encode("utf-8")).hexdigest()[:16]
        return f"verified-recovery-{fingerprint}",scenario,expected

    def _update_lesson(self, task, workflow, success, fingerprint, error, evidence):
        key = hashlib.sha256((self._norm(task) + "|" + self._norm(workflow)).encode()).hexdigest()[:20]
        rows = self.data["lessons"]
        row = next((x for x in rows if x.get("id") == key), None)
        if row is None:
            row = {"id": key, "task": task[:1000], "workflow": workflow[:500],
                   "attempts": 0, "successes": 0, "failures": 0,
                   "consecutive_successes": 0, "consecutive_failures": 0,
                   "confidence": 0.5, "failure_fingerprints": {},
                   "last_error": "", "updated_at": time.time(), "promoted": False}
            rows.append(row)
        row["attempts"] += 1
        if success:
            row["successes"] += 1
            row["consecutive_successes"] += 1
            row["consecutive_failures"] = 0
        else:
            row["failures"] += 1
            row["consecutive_failures"] += 1
            row["consecutive_successes"] = 0
            row["last_error"] = str(error or evidence.get("error_class", "unknown"))[:500]
            if fingerprint:
                counts = row["failure_fingerprints"]
                counts[fingerprint] = int(counts.get(fingerprint, 0)) + 1
        # Beta posterior mean: stable with small samples and resistant to one lucky run.
        row["confidence"] = round((row["successes"] + 1) / (row["attempts"] + 2), 4)
        row["updated_at"] = time.time()
        row["promoted"] = bool(row["attempts"] >= 3 and row["confidence"] >= 0.80
                                and row["consecutive_failures"] == 0)
        rows[:] = rows[-1000:]
        return dict(row)

    def recommend(self, task, limit=5):
        """Return evidence-weighted workflow recommendations with explanations."""
        target = self._norm(task)
        tokens = set(re.findall(r"[a-z0-9]+", target))
        candidates = []
        for row in self.data.get("lessons", []):
            rt = set(re.findall(r"[a-z0-9]+", self._norm(row.get("task", ""))))
            overlap = len(tokens & rt) / max(1, len(tokens | rt))
            if overlap < 0.08:
                continue
            attempts = int(row.get("attempts", 0))
            confidence = float(row.get("confidence", 0.0))
            regression_penalty = min(0.45, 0.12 * int(row.get("consecutive_failures", 0)))
            promotion_bonus = 0.08 if row.get("promoted") else 0.0
            score = max(0.0, min(1.0, 0.50 * overlap + 0.45 * confidence + promotion_bonus - regression_penalty))
            candidates.append({
                "workflow": row.get("workflow", ""), "task": row.get("task", ""),
                "score": round(score, 4), "similarity": round(overlap, 4),
                "confidence": round(confidence, 4), "attempts": attempts,
                "successes": int(row.get("successes", 0)),
                "failures": int(row.get("failures", 0)),
                "promoted": bool(row.get("promoted")),
                "consecutive_failures": int(row.get("consecutive_failures", 0)),
                "reason": "high evidence and task similarity" if row.get("promoted") else "supported by prior outcomes",
            })
        candidates.sort(key=lambda x: (x["score"], x["confidence"], x["successes"]), reverse=True)
        return candidates[:max(0, int(limit))]

    def consolidate(self, min_attempts=2):
        """Compress repeated outcomes into durable lessons without deleting evidence."""
        lessons = [x for x in self.data.get("lessons", []) if int(x.get("attempts", 0)) >= min_attempts]
        lessons.sort(key=lambda x: (x.get("confidence", 0), x.get("attempts", 0)), reverse=True)
        summary = {
            "version": self.VERSION,
            "generated_at": time.time(),
            "lesson_count": len(lessons),
            "promoted_count": sum(bool(x.get("promoted")) for x in lessons),
            "regression_count": len(self.data.get("regressions", [])),
            "verified_recovery_count": len(self.data.get("recoveries", [])),
            "top_lessons": lessons[:25],
        }
        self.data["consolidated"] = summary
        self._save()
        return summary

    def register_eval_case(self, name, task, expected=None, tags=None):
        case = {"name": str(name)[:160], "task": str(task)[:1000],
                "expected": expected, "tags": list(tags or [])[:20],
                "created_at": time.time()}
        existing = {x.get("name"): x for x in self.data.get("eval_cases", [])}
        existing[case["name"]] = case
        self.data["eval_cases"] = list(existing.values())[-500:]
        self._save()
        return case

    def grade_eval(self, name, *, success, score=None, notes=""):
        for case in self.data.get("eval_cases", []):
            if case.get("name") == name:
                result = {"success": bool(success), "score": max(0.0, min(1.0, float(score if score is not None else (1.0 if success else 0.0)))),
                          "notes": str(notes)[:1000], "graded_at": time.time()}
                case.setdefault("runs", []).append(result)
                case["runs"] = case["runs"][-20:]
                self._save()
                return result
        raise KeyError(name)

    def regressions(self, limit=20):
        """Identify workflows that were once strong but recently failed."""
        rows = []
        for row in self.data.get("lessons", []):
            if int(row.get("consecutive_failures", 0)) > 0 and int(row.get("successes", 0)) > 0:
                rows.append({"workflow": row.get("workflow"), "task": row.get("task"),
                             "confidence": row.get("confidence", 0),
                             "consecutive_failures": row.get("consecutive_failures", 0),
                             "last_error": row.get("last_error", "")})
        rows.sort(key=lambda x: x["consecutive_failures"], reverse=True)
        return rows[:max(0, int(limit))]

    def stats(self):
        total = len(self.store.records)
        success = sum(1 for r in self.store.records if r.success)
        return {"version": self.VERSION, "experience_records": total,
                "successful": success, "failed": total - success,
                "lessons": len(self.data.get("lessons", [])),
                "promoted": sum(bool(x.get("promoted")) for x in self.data.get("lessons", [])),
                "eval_cases": len(self.data.get("eval_cases", [])),
                "regression_seeds": len(self.data.get("regressions", [])),
                "verified_recoveries": len(self.data.get("recoveries", [])),
                "regressions": len(self.regressions())}
