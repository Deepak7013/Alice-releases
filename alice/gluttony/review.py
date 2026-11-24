"""Durable, per-capability human review for quarantined DEVOUR reports."""
from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from ..security.ingest_guard import IngestGuard
from .assimilation import license_requires_review


class DevourReviewError(ValueError):
    pass


class DevourReviewStore:
    SCHEMA=1
    _NAME=re.compile(r"^[a-z0-9][a-z0-9_.-]{0,79}$")
    DECISIONS={"reuse_compatible_component","integrate_behind_alice_interface","implement_native_equivalent"}

    def __init__(self,root):
        self.root=Path(root).resolve()
        self.base=self.root/"alice_workspace"/"gluttony"/"devour"
        self.base.mkdir(parents=True,exist_ok=True)
        self.path=self.base/"capability_approvals.json"
        self.guard=IngestGuard()
        self._lock=threading.RLock()

    @staticmethod
    def _sha(data):
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _canonical(value):
        return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(",",":"),default=str).encode("utf-8")

    def _report(self,report_path):
        raw=Path(report_path).expanduser()
        if raw.is_symlink(): raise DevourReviewError("DEVOUR report symlinks cannot be approved")
        try: path=raw.resolve(strict=True)
        except (OSError,RuntimeError,ValueError) as exc: raise DevourReviewError("DEVOUR report is unavailable") from exc
        single=path.name.startswith("DIGEST_")
        multi=path.name.startswith("MULTI_DIGEST_")
        if path.parent!=self.base.resolve() or not (single or multi) or path.suffix.casefold()!=".json":
            raise DevourReviewError("Only a verified quarantined DEVOUR report can enter capability review")
        try:
            content=path.read_bytes()
            if len(content)>8_000_000: raise DevourReviewError("DEVOUR report exceeds the review size limit")
            report=json.loads(content.decode("utf-8"))
        except DevourReviewError: raise
        except Exception as exc: raise DevourReviewError("DEVOUR report is not readable JSON") from exc
        if not isinstance(report,dict):
            raise DevourReviewError("DEVOUR report is not a completed analysis")
        if multi:
            return self._multi_report_info(path,content,report)
        if report.get("status")!="digested":
            raise DevourReviewError("DEVOUR report is not a completed single-source digest")
        policy=report.get("policy")
        if (not isinstance(policy,dict) or policy.get("executed_external_code") is not False
                or policy.get("activated_external_code") is not False
                or policy.get("native_reimplementation_required") is not True):
            raise DevourReviewError("DEVOUR report does not prove the source remained inactive")
        try:
            quarantine=Path(report["quarantine"]).resolve(strict=True)
            acquired=Path(report["acquired_source"]).resolve(strict=True)
        except Exception as exc:
            raise DevourReviewError("DEVOUR quarantine paths are invalid") from exc
        if (quarantine.parent!=self.base.resolve() or not quarantine.name.startswith("job_")
                or (acquired!=quarantine and quarantine not in acquired.parents)
                or not acquired.is_dir()):
            raise DevourReviewError("DEVOUR source is outside its expected quarantine")
        if any(entry.is_symlink() for entry in acquired.rglob("*")):
            raise DevourReviewError("DEVOUR quarantine contains a symbolic link")
        try: tree_sha=self.guard.digest_tree(acquired)
        except Exception as exc: raise DevourReviewError("DEVOUR quarantine cannot be rehashed") from exc
        if tree_sha!=report.get("tree_sha256"):
            raise DevourReviewError("DEVOUR quarantined source no longer matches its recorded SHA-256")
        architecture=report.get("architecture",{})
        inventory={}
        if report.get("analysis_schema_version")==2:
            try:
                from .assimilation import AssimilationEngine
                analyzer=AssimilationEngine(self.root)
                inventory=analyzer._inventory(acquired)
                architecture=analyzer._analyze(acquired,inventory)
            except Exception as exc:
                raise DevourReviewError("DEVOUR source inventory could not be independently recomputed") from exc
            if (architecture!=report.get("architecture")
                    or {key:value for key,value in inventory.items() if key!="files"}!=report.get("inventory")):
                raise DevourReviewError("DEVOUR static function or file inventory does not match the current quarantined source")
        security=report.get("security")
        if not isinstance(security,dict): raise DevourReviewError("DEVOUR report is missing security results")
        current_security=self.guard.scan_tree(acquired)
        if any(security.get(field)!=current_security.get(field) for field in ("threat_count","files_scanned")):
            raise DevourReviewError("DEVOUR security scan evidence no longer matches the quarantine")
        license_info=report.get("license")
        candidates=report.get("capability_candidates")
        if not isinstance(license_info,dict) or not isinstance(candidates,list):
            raise DevourReviewError("DEVOUR report is missing license or capability candidates")
        by_name={}
        for candidate in candidates:
            if not isinstance(candidate,dict): continue
            name=str(candidate.get("name","")).strip().lower()
            if not self._NAME.fullmatch(name) or name in by_name:
                raise DevourReviewError("DEVOUR report contains invalid or duplicate capability names")
            by_name[name]=candidate
        license_kind=str(license_info.get("kind","Unknown"))[:120]
        license_review_required=license_requires_review(license_kind)
        license_summary={**license_info,"kind":license_kind,"review_required":license_review_required}
        source_trees=[{"source_index":1,"source_identity":str(report.get("source","")),
                       "source_revision":None,"source_label":str(report.get("source_label","")),
                       "tree_sha256":tree_sha}]
        evidence_by_capability={name:{"name":name,"evidence_score":candidate.get("evidence_score",0),
            "evidence_terms":candidate.get("evidence_terms",[]),"evidence_files":candidate.get("evidence_files",[]),
            "sources":[{"source_index":1,"source_label":str(report.get("source_label","")),
                "source_identity":str(report.get("source","")),"source_revision":None,
                "tree_sha256":tree_sha,"candidate":candidate}]}
            for name,candidate in by_name.items()}
        return {"path":path,"report":report,"report_sha256":self._sha(content),
                "tree_sha256":tree_sha,"security":current_security,"source_trees":source_trees,
                "license":license_summary,"candidates":by_name,
                "evidence_by_capability":evidence_by_capability,"multi_source":False,
                "architecture":architecture,"inventory":inventory}

    def _multi_report_info(self,path,content,report):
        """Reverify every quarantined child before allowing aggregate human review."""
        rows=report.get("sources"); comparison=report.get("capability_comparison")
        policy=report.get("policy")
        if (report.get("status")!="analyzed" or report.get("job_type")!="multi_source_devour"
                or not isinstance(rows,list) or not 2<=len(rows)<=8
                or report.get("source_count")!=len(rows) or not isinstance(comparison,dict)
                or not isinstance(comparison.get("candidates"),list)
                or not isinstance(report.get("source_quality_comparison"),dict)
                or not isinstance(policy,dict)
                or policy.get("executed_external_code") is not False
                or policy.get("activated_external_code") is not False
                or policy.get("promotion_enabled") is not False
                or policy.get("auto_upgrade_enabled") is not False
                or policy.get("native_reimplementation_required") is not True):
            raise DevourReviewError("Multi-source report is missing required inactive-source evidence")
        try:
            from .evolver import DevourEngine
            engine=DevourEngine(self.root,self_manager=object())
            raw_sources=[row["source"] for row in rows]
            result={"status":"analyzed","job_id":report.get("job_id"),"report":str(path),
                "source_count":len(rows),
                "combined_tree_sha256":report.get("combined_tree_sha256"),
                "capability_candidates":comparison["candidates"],
                "license_comparison":report.get("license_comparison"),
                "source_quality_comparison":report.get("source_quality_comparison"),
                "security":{"source_threat_counts":[row.get("security",{}).get("threat_count",0) for row in rows]},
                "policy":policy}
            observed=engine.verify_multi_postcondition({"sources":raw_sources},result)
            if not observed.ok: raise ValueError(observed.reason or "postcondition failed")
        except Exception as exc:
            raise DevourReviewError("Multi-source quarantine or aggregate evidence failed independent verification") from exc

        trees=[]; details=[]; children={}; threat_count=0; files_scanned=0
        for row in rows:
            # Do not trust a child-report path merely because the aggregate verifier
            # accepted the report structure. Resolve and constrain it before reading:
            # aggregate JSON is untrusted input and must not become an arbitrary-file reader.
            raw_child = Path(str(row.get("report", ""))).expanduser()
            if raw_child.is_symlink():
                raise DevourReviewError("Multi-source child report symlinks cannot be reviewed")
            try:
                child_path = raw_child.resolve(strict=True)
            except (OSError, RuntimeError, ValueError) as exc:
                raise DevourReviewError("Multi-source child report is unavailable") from exc
            base_path = self.base.resolve()
            if (base_path not in child_path.parents
                    or child_path.name != "analysis_report.json"
                    or child_path.suffix.casefold() != ".json"
                    or child_path.stat().st_size > 8_000_000):
                raise DevourReviewError("Multi-source child report is outside the bounded DEVOUR report store")
            try:
                child = json.loads(child_path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise DevourReviewError("Multi-source child report is not valid JSON") from exc
            if (not isinstance(child, dict)
                    or child.get("status") not in {"analyzed", "digested"}
                    or not isinstance(child.get("tree_sha256"), str)):
                raise DevourReviewError("Multi-source child report is not a completed digest")
            index=row["source_index"]; children[index]=child
            trees.append({"source_index":index,"source_identity":row["source_identity"],
                "source_revision":row.get("source_revision"),"source_label":row.get("source_label"),
                "tree_sha256":row["tree_sha256"]})
            security=row["security"]
            threat_count+=int(security.get("threat_count",0)); files_scanned+=int(security.get("files_scanned",0))
            architecture=child.get("architecture",{})
            project=architecture.get("project",{}) if isinstance(architecture,dict) else {}
            details.append({"source_index":index,"source_identity":row["source_identity"],
                "source_label":row.get("source_label",""),"source_revision":row.get("source_revision"),
                "tree_sha256":row["tree_sha256"],"license":row["license"],
                "security":{"threat_count":security.get("threat_count",0),
                    "files_scanned":security.get("files_scanned",0)},
                "file_count":row.get("file_count"),"total_bytes":row.get("total_bytes"),
                "source_quality":row.get("source_quality"),
                "dependencies":project.get("dependencies",[])})

        candidates={}
        for aggregate in comparison["candidates"]:
            if not isinstance(aggregate,dict): raise DevourReviewError("Invalid aggregate capability candidate")
            name=str(aggregate.get("name"," ")).strip().lower()
            if not self._NAME.fullmatch(name) or name in candidates:
                raise DevourReviewError("Multi-source report contains invalid or duplicate capability names")
            source_evidence=[]; terms=[]; evidence_files=[]; score=0
            for source_ref in aggregate.get("sources",[]):
                if not isinstance(source_ref,dict): raise DevourReviewError("Invalid aggregate source evidence")
                index=source_ref.get("source_index"); child=children.get(index)
                if child is None: raise DevourReviewError("Capability references an unknown source")
                candidate=next((item for item in child.get("capability_candidates",[])
                    if isinstance(item,dict) and item.get("name")==name),None)
                if candidate is None: raise DevourReviewError("Capability is absent from its child report")
                row=rows[int(index)-1]
                source_evidence.append({"source_index":index,"source_label":row.get("source_label",""),
                    "source_identity":row["source_identity"],"source_revision":row.get("source_revision"),
                    "tree_sha256":row["tree_sha256"],"candidate":candidate})
                score+=int(candidate.get("evidence_score",0))
                terms.extend(str(term) for term in candidate.get("evidence_terms",[]))
                evidence_files.extend(f"source_{int(index):02d}/{item}" for item in candidate.get("evidence_files",[]))
            if not source_evidence: raise DevourReviewError("Multi-source capability has no child evidence")
            candidates[name]={"name":name,"evidence_score":score,"evidence_source_count":len(source_evidence),
                "evidence_terms":list(dict.fromkeys(terms))[:40],"evidence_files":list(dict.fromkeys(evidence_files))[:40],
                "sources":source_evidence,"approval":aggregate.get("approval",{})}

        license_kinds=sorted({str(row["license"].get("kind","Unknown")) for row in rows})
        license_info={"kind":license_kinds[0] if len(license_kinds)==1 else "Mixed: "+", ".join(license_kinds),
            "review_required":any(self._license_review_required(row["license"].get("kind")) for row in rows),
            "sources":[{"source_index":row["source_index"],"source_label":row.get("source_label",""),
                "kind":row["license"].get("kind","Unknown"),
                "review_required":self._license_review_required(row["license"].get("kind"))} for row in rows]}
        return {"path":path,"report":report,"report_sha256":self._sha(content),
            "tree_sha256":report["combined_tree_sha256"],"source_trees":trees,"source_details":details,
            "security":{"threat_count":threat_count,"files_scanned":files_scanned,
                "per_source":[{**item["security"],"source_index":item["source_index"],
                    "source_label":item["source_label"]} for item in details]},
            "license":license_info,"candidates":candidates,"evidence_by_capability":candidates,
            "child_by_index":children,"multi_source":True}

    @staticmethod
    def _license_review_required(kind):
        return license_requires_review(kind)

    def _load(self):
        if not self.path.exists(): return {"schema":self.SCHEMA,"records":[]}
        try: data=json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc: raise DevourReviewError("DEVOUR approval ledger is unreadable; refusing to overwrite it") from exc
        if not isinstance(data,dict) or data.get("schema")!=self.SCHEMA or not isinstance(data.get("records"),list):
            raise DevourReviewError("DEVOUR approval ledger has an unsupported schema")
        return data

    def _save(self,data):
        tmp=self.path.with_name(self.path.name+".tmp")
        tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        tmp.replace(self.path)

    @staticmethod
    def _candidate_sha(candidate):
        return hashlib.sha256(DevourReviewStore._canonical(candidate)).hexdigest()

    def inspect(self,report_path):
        with self._lock:
            info=self._report(report_path)
            ledger=self._load()
            latest={}
            for row in ledger["records"]:
                if not isinstance(row,dict): continue
                key=(row.get("report_sha256"),row.get("capability"))
                latest[key]=row
            rows=[]
            assessment_obj=info["report"].get("alice_capability_assessment",{})
            assessment=assessment_obj.get("capabilities",[]) if isinstance(assessment_obj,dict) else []
            if not isinstance(assessment,list): assessment=[]
            assessed={str(row.get("name","")).strip().lower():row for row in assessment if isinstance(row,dict)}
            for name,candidate in sorted(info["candidates"].items()):
                record=latest.get((info["report_sha256"],name),{})
                approved=(record.get("approved") is True
                    and record.get("tree_sha256")==info["tree_sha256"]
                    and record.get("candidate_sha256")==self._candidate_sha(candidate)
                    and (record.get("source_tree_sha256s")==info["source_trees"]
                         or (not info["multi_source"] and "source_tree_sha256s" not in record))
                    and record.get("decision","implement_native_equivalent") in self.DECISIONS)
                recommendation=assessed.get(name,{}).get("recommendation","manual_review")
                if info["multi_source"]:
                    recommendations=[]
                    for detail in candidate.get("sources",[]):
                        child=info["child_by_index"].get(detail["source_index"],{})
                        child_assess=child.get("alice_capability_assessment",{})
                        child_rows=child_assess.get("capabilities",[]) if isinstance(child_assess,dict) else []
                        match=next((item for item in child_rows if isinstance(item,dict)
                                    and item.get("name")==name),{})
                        recommendations.append(str(match.get("recommendation","manual_review")))
                    recommendation=(recommendations[0] if recommendations and len(set(recommendations))==1
                        else "mixed: "+", ".join(dict.fromkeys(recommendations)))
                rows.append({"name":name,"evidence_score":candidate.get("evidence_score",0),
                    "evidence_terms":candidate.get("evidence_terms",[])[:20],
                    "evidence_files":candidate.get("evidence_files",[])[:20],
                    "evidence_source_count":candidate.get("evidence_source_count",1),
                    "sources":candidate.get("sources",[]),"recommendation":recommendation,
                    "approved":approved,
                    "decision":record.get("decision","implement_native_equivalent") if approved else None,
                    "approved_at":record.get("approved_at") if approved else None,
                    "ui_request":record.get("ui_request","") if approved else ""})
            source_label=str(info["report"].get("source_label", ""))
            if info["multi_source"]:
                source_label="; ".join(str(row.get("source_label") or row.get("source_identity") or "source")
                                        for row in info["source_details"])
            return {"report":str(info["path"]),"report_sha256":info["report_sha256"],
                "tree_sha256":info["tree_sha256"],"source_label":source_label[:320],
                "multi_source":info["multi_source"],"source_trees":info["source_trees"],
                "source_details":info.get("source_details",[]),"license":info["license"],
                "security":info["security"],"capabilities":rows,
                "architecture":info.get("architecture",{}),
                "child_by_index":info.get("child_by_index",{})}

    def latest_report_path(self):
        reports=sorted([*self.base.glob("DIGEST_*.json"),*self.base.glob("MULTI_DIGEST_*.json")],
                       key=lambda path:path.stat().st_mtime,reverse=True)
        for path in reports:
            try:
                self.inspect(path)
                return path
            except DevourReviewError:
                continue
        return None

    def _record(self,report_path,capability,approved,*,confirmed,reviewer,
                decision="implement_native_equivalent",ui_request=""):
        if confirmed is not True: raise DevourReviewError("Explicit per-capability confirmation is required")
        name=str(capability).strip().lower()
        if not self._NAME.fullmatch(name): raise DevourReviewError("Invalid capability name")
        decision=str(decision or "").strip().lower()
        if approved and decision not in self.DECISIONS:
            raise DevourReviewError("Choose a supported per-capability DEVOUR decision")
        ui_request=" ".join(str(ui_request or "").split())
        if len(ui_request)>1000:
            raise DevourReviewError("Optional UI adaptation guidance must be at most 1000 characters")
        if not approved:
            decision="revoked"
        with self._lock:
            info=self._report(report_path)
            candidate=info["candidates"].get(name)
            if candidate is None: raise DevourReviewError("Capability is not present in this DEVOUR report")
            if approved and decision=="reuse_compatible_component":
                recommendations=[]
                if info["multi_source"]:
                    for child in info["child_by_index"].values():
                        assessment=child.get("alice_capability_assessment",{})
                        rows=assessment.get("capabilities",[]) if isinstance(assessment,dict) else []
                        match=next((row for row in rows if isinstance(row,dict) and row.get("name")==name),{})
                        recommendations.append(str(match.get("recommendation","manual_review")))
                else:
                    assessment=info["report"].get("alice_capability_assessment",{})
                    rows=assessment.get("capabilities",[]) if isinstance(assessment,dict) else []
                    match=next((row for row in rows if isinstance(row,dict) and row.get("name")==name),{})
                    recommendations.append(str(match.get("recommendation","manual_review")))
                compatible_existing={"compare_and_improve_only_if_source_is_better","improve_native_capability"}
                if not any(item in compatible_existing for item in recommendations):
                    raise DevourReviewError("No compatible existing ALICE component is evidenced for this capability")
            data=self._load()
            row={"report_sha256":info["report_sha256"],"tree_sha256":info["tree_sha256"],
                 "source_tree_sha256s":info["source_trees"],
                 "capability":name,"candidate_sha256":self._candidate_sha(candidate),
                 "approved":bool(approved),"decision":decision,"reviewer":str(reviewer or "local_user")[:80],
                 "ui_adaptation_approved":bool(approved and ui_request),"ui_request":ui_request if approved else "",
                 "approval_method":"explicit_per_capability_ui_confirmation",
                 "approved_at":datetime.now(timezone.utc).isoformat()}
            data["records"]=(data["records"]+[row])[-5000:]
            self._save(data)
            return row

    def approve_capability(self,report_path,capability,*,confirmed=False,reviewer="local_user",
                           decision="implement_native_equivalent",ui_request=""):
        return self._record(report_path,capability,True,confirmed=confirmed,reviewer=reviewer,
                            decision=decision,ui_request=ui_request)

    def revoke_capability(self,report_path,capability,*,confirmed=False,reviewer="local_user"):
        return self._record(report_path,capability,False,confirmed=confirmed,reviewer=reviewer)

    def approval_evidence(self,report_path,capabilities=None):
        with self._lock:
            info=self._report(report_path)
            view=self.inspect(report_path)
            approved={row["name"]:row for row in view["capabilities"] if row["approved"]}
            if capabilities is not None and (not isinstance(capabilities,(list,tuple)) or not capabilities):
                raise DevourReviewError("Requested capability approvals must be a non-empty list")
            requested=sorted(set(str(name).strip().lower() for name in capabilities)) if capabilities is not None else sorted(approved)
            if not requested or any(name not in approved for name in requested):
                raise DevourReviewError("Every selected capability needs a current individual approval")
            ledger=self._load(); latest={}
            for row in ledger["records"]:
                if isinstance(row,dict): latest[(row.get("report_sha256"),row.get("capability"))]=row
            records=[latest[(info["report_sha256"],name)] for name in requested]
            return {"report_sha256":info["report_sha256"],"tree_sha256":info["tree_sha256"],
                    "source_tree_sha256s":info["source_trees"],"approvals":records,
                    "decisions":{row["capability"]:row.get("decision","implement_native_equivalent")
                        for row in records},
                    "ui_requests":{row["capability"]:row.get("ui_request","")
                        for row in records if row.get("ui_adaptation_approved") is True},
                    "native_evidence":self._native_evidence(info,requested),
                    "provenance":self._provenance(info,requested)}

    def _native_evidence(self,info,requested):
        if not info["multi_source"]:
            report=info["report"]
            candidates=[dict(info["candidates"][name]) for name in requested]
            files={item for row in candidates for item in row.get("evidence_files",[])}
            plan=[row for row in report.get("reimplementation_plan",[])
                if isinstance(row,dict) and str(row.get("capability"," ")).strip().lower() in requested]
            source_architecture=report.get("architecture",{})
            architecture={key:value for key,value in source_architecture.items() if key!="file_catalog"}
            architecture["modules"]=[{**module,
                "symbol_names":module.get("symbol_names",[])[:100],
                "methods":module.get("methods",[])[:100],"fields":module.get("fields",[])[:100]}
                for module in source_architecture.get("modules",[])
                if isinstance(module,dict) and module.get("path") in files][:80]
            project=architecture.get("project",{})
            if isinstance(project,dict):
                project={**project,"dependencies":project.get("dependencies",[])[:100],
                    "manifests":project.get("manifests",[])[:30],
                    "declared_scripts":project.get("declared_scripts",[])[:100],
                    "test_files":project.get("test_files",[])[:100]}
                architecture["project"]=project
            return {"source":report.get("source"),"license":info["license"],"security":info["security"],
                "architecture":architecture,"candidates":candidates,"plan":plan,
                "samples":[row for row in report.get("source_samples",[])
                    if isinstance(row,dict) and row.get("path") in files]}
        children=info["child_by_index"]; candidates=[]; plans=[]; samples=[]
        for name in requested:
            aggregate=info["evidence_by_capability"][name]
            native={"name":name,"evidence_score":aggregate["evidence_score"],
                "evidence_terms":aggregate["evidence_terms"],"evidence_files":aggregate["evidence_files"],
                "sources":[]}
            for detail in aggregate["sources"]:
                index=detail["source_index"]; child=children[index]; candidate=detail["candidate"]
                native["sources"].append({**candidate,"source_index":index,
                    "source_label":detail["source_label"],"source_identity":detail["source_identity"],
                    "source_revision":detail["source_revision"],"tree_sha256":detail["tree_sha256"]})
                files=set(candidate.get("evidence_files",[]))
                for sample in child.get("source_samples",[]):
                    if isinstance(sample,dict) and sample.get("path") in files:
                        samples.append({**sample,"path":f"source_{int(index):02d}/{sample['path']}",
                            "source_index":index,"source_label":detail["source_label"],
                            "source_tree_sha256":detail["tree_sha256"]})
                plans.extend({**row,"source_index":index,"source_label":detail["source_label"],
                    "source_tree_sha256":detail["tree_sha256"]}
                    for row in child.get("reimplementation_plan",[])
                    if isinstance(row,dict) and str(row.get("capability"," ")).strip().lower()==name)
            candidates.append(native)
        return {"source":"multi-source DEVOUR analysis","license":info["license"],
            "security":info["security"],"architecture":{"per_source":[{
                "source_index":row["source_index"],"source_label":row["source_label"],
                "dependencies":row["dependencies"]} for row in info["source_details"]]},
            "candidates":candidates,"plan":plans,"samples":samples}

    @staticmethod
    def _provenance(info,requested):
        source_rows=[{key:row.get(key) for key in
            ("source_index","source_identity","source_revision","tree_sha256")}
            for row in info["source_trees"]]
        report=info["report"]
        label=report.get("source_label") or (
            "multi-source ("+str(len(source_rows))+" sources)" if info["multi_source"] else "")
        acquisition=report.get("acquisition",{})
        return {"source_label":label,
            "source_fingerprint_sha256":hashlib.sha256(DevourReviewStore._canonical(source_rows)).hexdigest(),
            "report_sha256":info["report_sha256"],"tree_sha256":info["tree_sha256"],
            "source_tree_sha256s":info["source_trees"],
            "acquisition_method":"multi_source" if info["multi_source"] else
                str(acquisition.get("method","unknown"))[:80],
            "license":info["license"],"security":info["security"],
            "candidate_capabilities":requested,"external_code_executed":False,
            "external_code_activated":False}
