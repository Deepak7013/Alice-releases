"""ALICE Devour -> Digest -> Reimplement bridge.

External projects are treated strictly as untrusted source material. This module
never imports or executes acquired project code. It creates a bounded capability
digest and, only after explicit approval through the caller, asks ALICE's governed
self-engineering system to reimplement selected capabilities natively.
"""
from __future__ import annotations
import hashlib, json, os, re, time
from pathlib import Path
from .assimilation import AssimilationEngine, AssimilationError, license_requires_review
from .assessment import assess_capabilities
from .discovery import GitHubRepositoryDiscovery
from .intake import IntakeError, LocalInputAdapter
from .installer_analysis import inspect_installer as inspect_windows_installer

class DevourError(RuntimeError):
    pass

class DevourEngine:
    MAX_DIGEST_BYTES = 8_000_000
    MAX_SNIPPETS = 80
    MAX_MULTI_SOURCES = 8
    MAX_MULTI_TOTAL_BYTES = 500_000_000
    MAX_MULTI_FILES = 32_000
    SECRET_ASSIGNMENT = re.compile(
        r'''(?im)(["']?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|passwd|secret|credential)["']?\s*[:=]\s*["']?)[^"'\r\n,;}\s]+'''
    )
    def __init__(self, root=None, gluttony=None, self_manager=None, discovery=None, capability_manager=None):
        self.root=Path(root or Path(__file__).resolve().parents[2]).resolve()
        self.gluttony=gluttony or AssimilationEngine(self.root)
        if self_manager is None:
            from ..maintenance.self_manager import SelfManager
            self_manager=SelfManager(self.root, capability_manager=capability_manager)
        self.self_manager=self_manager
        self.base=self.root/"alice_workspace"/"gluttony"/"devour"
        self.base.mkdir(parents=True,exist_ok=True)
        self.intake=LocalInputAdapter(max_files=self.gluttony.MAX_FILES,
                                      max_total_bytes=self.gluttony.MAX_TOTAL_BYTES)
        self.discovery=discovery or GitHubRepositoryDiscovery()
        self.capability_manager=capability_manager
        # A caller-supplied manager may be a restricted adapter (or test double)
        # with slots/read-only attributes. The engine owns its capability manager;
        # only synchronize the optional SelfManager hook when it exposes one.
        if capability_manager is not None and hasattr(self.self_manager, "capability_manager"):
            self.self_manager.capability_manager=capability_manager

    def discover_candidates(self, capability, limit=5):
        result=self.discovery.discover(capability,limit=limit)
        stamp=time.strftime("%Y%m%d_%H%M%S")+"_"+hashlib.sha256(result["query"].encode()).hexdigest()[:8]
        report_path=self.base/("DISCOVERY_"+stamp+".json")
        report_path.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding="utf-8")
        result["report"]=str(report_path)
        return result

    def devour_objective(self, objective, *, candidate_limit=5, source_count=3):
        """Discover, rank, and quarantine public candidates for an objective without a manual repo pick."""
        objective=" ".join(str(objective or "").split())
        if len(objective)<3 or len(objective)>500:
            raise DevourError("Describe the capability objective in 3 to 500 characters.")
        if isinstance(source_count,bool) or not isinstance(source_count,int) or not 1<=source_count<=self.MAX_MULTI_SOURCES:
            raise DevourError(f"Objective source count must be from 1 to {self.MAX_MULTI_SOURCES}.")
        if isinstance(candidate_limit,bool) or not isinstance(candidate_limit,int) or not source_count<=candidate_limit<=10:
            raise DevourError("Candidate limit must be at least the requested source count and no greater than 10.")
        discovery=self.discover_candidates(objective,limit=candidate_limit)
        candidates=[row for row in discovery.get("candidates",[]) if isinstance(row,dict)
            and str(row.get("url"," ")).startswith("https://github.com/")]
        selected=candidates[:source_count]
        if not selected:
            raise DevourError("Public-source discovery found no usable repositories for this objective.")
        urls=[row["url"] for row in selected]
        if len(urls)==1:
            analysis=self.devour(urls[0])
            analysis_path=analysis.get("report")
            analysis_type="single_source"
        else:
            analysis=self.devour_many(urls)
            analysis_path=analysis.get("report")
            analysis_type="multi_source"
        discovery_path=Path(discovery["report"])
        workflow={"status":"analyzed","workflow":"objective_driven_devour","objective":objective,
            "discovery_report":str(discovery_path),
            "discovery_report_sha256":hashlib.sha256(discovery_path.read_bytes()).hexdigest(),
            "analysis_report":analysis_path,
            "analysis_report_sha256":hashlib.sha256(Path(analysis_path).read_bytes()).hexdigest(),
            "analysis_type":analysis_type,
            "selected_candidates":[{key:row.get(key) for key in
                ("rank","name","url","score","discovery_score","relevance_score","stars","language","license")}
                for row in selected],
            "selection_policy":"top advisory discovery rank; selection authorizes quarantine analysis only",
            "policy":{"executed_external_code":False,"approved_capability_count":0,
                "promotion_enabled":False,"auto_upgrade_enabled":False}}
        stamp=time.strftime("%Y%m%d_%H%M%S")+"_"+hashlib.sha256(
            (objective+str(analysis_path)).encode("utf-8")).hexdigest()[:10]
        workflow_path=self.base/("OBJECTIVE_"+stamp+".json")
        self._write_json(workflow_path,workflow)
        return {**analysis,"objective":objective,"selected_candidates":workflow["selected_candidates"],
            "discovery_report":str(discovery_path),"objective_workflow_report":str(workflow_path),
            "analysis_type":analysis_type,"objective_policy":workflow["policy"]}

    def _copy_local(self, source, work, *, intake=None):
        p=Path(source).expanduser()
        try:
            staged=(intake or self.intake).stage(p,work)
        except IntakeError as exc:
            raise DevourError(str(exc)) from exc
        return staged.source,{"method":staged.method,"source":str(p),
                              "input_format":staged.input_format,
                              "files_copied":staged.files_copied,
                              "bytes_copied":staged.bytes_copied,
                              "input_sha256":staged.input_sha256,
                              "source_size":staged.source_size}

    def _sample_source(self, source, inventory):
        rows=[]; used=0
        for item in inventory["files"]:
            if item["ext"] not in self.gluttony.CODE_EXTENSIONS or item["size"]>120_000: continue
            try: text=(source/item["path"]).read_text(errors="replace")[:12_000]
            except Exception: continue
            if not text.strip(): continue
            text=self.SECRET_ASSIGNMENT.sub(r"\1[REDACTED]",text)
            if used+len(text.encode())>self.MAX_DIGEST_BYTES: break
            rows.append({"path":item["path"],"language":item["ext"],"content":text})
            used+=len(text.encode())
            if len(rows)>=self.MAX_SNIPPETS: break
        return rows

    def _capability_plan(self, caps, analysis, license_info):
        assessment=assess_capabilities(self.root,caps,analysis); plan=[]
        project=analysis.get("project",{})
        candidate_tests=project.get("test_files",analysis.get("tests",[]))
        dependency_count=len(project.get("dependencies",[]))
        for c in caps:
            row=next((x for x in assessment["capabilities"] if x["name"]==c.get("name")),{})
            current=(self.capability_manager.status(c["name"])
                     if self.capability_manager is not None and self.capability_manager.get(c["name"])
                     else {"known":False,"status":"unknown","verified":False})
            acceptance=[
                {"check":"native_implementation_tests_pass","minimum_passing_tests":1},
                {"check":"external_candidate_code_never_executes","required":True},
                {"check":"capability_registry_records_provenance_and_evidence","required":True},
            ]
            if candidate_tests:
                acceptance.append({"check":"candidate_test_suite_reviewed_without_execution_during_analysis",
                                   "available_test_files":len(candidate_tests)})
            plan.append({
                "capability":c["name"],
                "specification":{
                    "objective":f"Reimplement the evidenced {c['name'].replace('_',' ')} behavior natively behind an ALICE-owned interface.",
                    "evidence_terms":c.get("evidence_terms",[]),
                    "evidence_files":c.get("evidence_files",[]),
                    "candidate_test_files":list(candidate_tests[:100]),
                    "declared_dependency_count":dependency_count,
                    "acceptance_criteria":acceptance,
                },
                "evidence_score":c.get("evidence_score",0),
                "recommended_action":row.get("recommendation","manual_review"),
                "execution":"never_execute_external_code",
                "license_review_required":license_requires_review(license_info.get("kind")),
                "alice_source_status":row.get("status","unknown"),
                "alice_source_paths":row.get("matched_paths",[]),
                "alice_live_capability":current,
            })
        return plan,assessment

    def latest_report(self):
        reports=sorted(self.base.glob("DIGEST_*.json"),key=lambda p:p.stat().st_mtime,reverse=True)
        if not reports:return {"ok":False,"message":"No Devour digest reports are available yet."}
        p=reports[0]; data=json.loads(p.read_text(encoding="utf-8"))
        return {"ok":True,"report":str(p),"source":data.get("source"),
                "acquisition":data.get("acquisition",{}),
                "capability_candidates":data.get("capability_candidates",[]),
                "alice_capability_assessment":data.get("alice_capability_assessment",{}),
                "architecture":data.get("architecture",{}),
                "source_samples":data.get("source_samples",[]),
                "security":data.get("security",{}),"license":data.get("license",{}),
                "policy":data.get("policy",{})}

    def inspect_installer(self, path):
        """Record read-only PE/hash/signature metadata for one installer."""
        try:
            result=inspect_windows_installer(path)
        except (OSError,ValueError) as exc:
            raise DevourError(str(exc)) from exc
        stamp=time.strftime("%Y%m%d_%H%M%S")+"_"+result["sha256"][:12]
        report_path=self.base/("INSTALLER_"+stamp+".json")
        self._write_json(report_path,result)
        return {**result,"report":str(report_path)}

    def devour(self, source, goal=None, auto_upgrade=False, approval_token=None):
        source=str(source).strip()
        if not source: raise DevourError("A ZIP, folder, or GitHub URL is required.")
        if auto_upgrade:
            raise DevourError("DEVOUR analysis cannot trigger native reimplementation from a caller-supplied token; approve capabilities individually in the DEVOUR Review workflow.")
        stamp=time.strftime("%Y%m%d_%H%M%S")+"_"+hashlib.sha256(source.encode()).hexdigest()[:8]
        work=self.base/("job_"+stamp); work.mkdir(parents=True,exist_ok=False)
        is_url=source.lower().startswith(("http://","https://"))
        try:
            if is_url:
                acquired,acq=self.gluttony._acquire(source,work)
                owner,repo=self.gluttony._repo_slug(source)
                source_label=f"{owner}/{repo}"
            else:
                acquired,acq=self._copy_local(source,work)
                source_label=Path(source).name
            guard=self.gluttony.guard.scan_tree(acquired)
            inventory=self.gluttony._inventory(acquired)
            analysis=self.gluttony._analyze(acquired,inventory)
            license_info=self.gluttony._license(acquired)
            caps=self.gluttony._capabilities(acquired,inventory,analysis)
            digest=self.gluttony.guard.digest_tree(acquired)
            snippets=self._sample_source(acquired,inventory)
            plan,assessment=self._capability_plan(caps,analysis,license_info)
            report={"analysis_schema_version":2,"status":"digested","source":source,"source_label":source_label,
                    "quarantine":str(work),"acquired_source":str(acquired),
                    "tree_sha256":digest,"acquisition":acq,
                    "license":license_info,"security":guard,
                    "inventory":{k:v for k,v in inventory.items() if k!="files"},
                    "architecture":analysis,"capability_candidates":caps,
                    "alice_capability_assessment":assessment,
                    "reimplementation_plan":plan,"source_samples":snippets,
                    "policy":{"executed_external_code":False,"activated_external_code":False,
                              "native_reimplementation_required":True}}
            report_path=self.base/("DIGEST_"+stamp+".json")
            report_path.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
            result={"ok":True,"status":"digested","source":source,"report":str(report_path),
                    "tree_sha256":digest,"capabilities":caps,"security":guard,"license":license_info,
                    "alice_capability_assessment":assessment,
                    "recommended_capabilities":assessment.get("recommended_for_native_review",[])}
            return result
        except Exception:
            raise

    def verify_single_postcondition(self,args,result):
        """Independently re-read and reanalyze a completed single-source DEVOUR report."""
        from ..execution.postconditions import PostconditionResult
        try:
            if not isinstance(result,dict) or result.get("status")!="digested":
                raise ValueError("result_not_digested")
            raw=Path(result.get("report",""))
            if raw.is_symlink(): raise ValueError("report_symlink")
            path=raw.resolve(strict=True)
            if path.parent!=self.base.resolve() or not path.name.startswith("DIGEST_") or path.stat().st_size>self.MAX_DIGEST_BYTES:
                raise ValueError("report_outside_devour_store")
            report=json.loads(path.read_text(encoding="utf-8"))
            requested_source=(str(args.get("source","")).strip() if isinstance(args,dict) else "")
            if (report.get("status")!="digested" or report.get("source")!=result.get("source")
                    or (requested_source and report.get("source")!=requested_source)
                    or result.get("report")!=str(path)):
                raise ValueError("report_identity_mismatch")
            policy=report.get("policy")
            if (not isinstance(policy,dict) or policy.get("executed_external_code") is not False
                    or policy.get("activated_external_code") is not False
                    or policy.get("native_reimplementation_required") is not True):
                raise ValueError("source_policy_mismatch")
            raw_work=Path(report.get("quarantine","")); raw_source=Path(report.get("acquired_source",""))
            if raw_work.is_symlink() or raw_source.is_symlink(): raise ValueError("quarantine_symlink")
            work=raw_work.resolve(strict=True); source=raw_source.resolve(strict=True)
            if (work.parent!=self.base.resolve() or not work.name.startswith("job_")
                    or source!=work and work not in source.parents or not source.is_dir()
                    or any(item.is_symlink() for item in work.rglob("*"))):
                raise ValueError("quarantine_path_mismatch")
            guard=self.gluttony.guard.scan_tree(source)
            digest=self.gluttony.guard.digest_tree(source)
            inventory=self.gluttony._inventory(source)
            architecture=self.gluttony._analyze(source,inventory)
            license_info=self.gluttony._license(source)
            candidates=self.gluttony._capabilities(source,inventory,architecture)
            samples=self._sample_source(source,inventory)
            plan,assessment=self._capability_plan(candidates,architecture,license_info)
            if (digest!=report.get("tree_sha256") or digest!=result.get("tree_sha256")
                    or guard!=report.get("security") or guard!=result.get("security")
                    or license_info!=report.get("license") or license_info!=result.get("license")
                    or candidates!=report.get("capability_candidates") or candidates!=result.get("capabilities")
                    or architecture!=report.get("architecture")
                    or {key:value for key,value in inventory.items() if key!="files"}!=report.get("inventory")
                    or samples!=report.get("source_samples") or plan!=report.get("reimplementation_plan")
                    or assessment!=report.get("alice_capability_assessment")
                    or assessment!=result.get("alice_capability_assessment")):
                raise ValueError("single_source_analysis_mismatch")
            return PostconditionResult(True,{"observed":True,"report_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                "tree_sha256":digest,"security_rescanned":True,"analysis_recomputed":True},
                "single-source quarantine and analysis independently read back")
        except Exception as exc:
            return PostconditionResult(False,{"observed":False},
                f"single_source_postcondition_failed:{type(exc).__name__}")

    def verify_objective_postcondition(self,args,result):
        """Verify discovery provenance, automatic candidate choice, and the resulting DEVOUR analysis."""
        from ..execution.postconditions import PostconditionResult
        try:
            if not isinstance(result,dict) or result.get("status") not in {"digested","analyzed"}:
                raise ValueError("objective_result_not_analyzed")
            raw_workflow=Path(result.get("objective_workflow_report",""))
            if raw_workflow.is_symlink(): raise ValueError("workflow_symlink")
            workflow_path=raw_workflow.resolve(strict=True)
            if (workflow_path.parent!=self.base.resolve() or not workflow_path.name.startswith("OBJECTIVE_")
                    or workflow_path.stat().st_size>self.MAX_DIGEST_BYTES):
                raise ValueError("workflow_outside_devour_store")
            workflow=json.loads(workflow_path.read_text(encoding="utf-8"))
            objective=" ".join(str((args or {}).get("objective","")).split()) if isinstance(args,dict) else ""
            if (workflow.get("status")!="analyzed" or workflow.get("workflow")!="objective_driven_devour"
                    or workflow.get("objective")!=objective or result.get("objective")!=objective
                    or workflow.get("analysis_report")!=result.get("report")
                    or workflow.get("analysis_type")!=result.get("analysis_type")
                    or workflow.get("selected_candidates")!=result.get("selected_candidates")):
                raise ValueError("objective_workflow_mismatch")
            policy=workflow.get("policy")
            if (not isinstance(policy,dict) or policy.get("executed_external_code") is not False
                    or policy.get("approved_capability_count")!=0
                    or policy.get("promotion_enabled") is not False
                    or policy.get("auto_upgrade_enabled") is not False):
                raise ValueError("objective_workflow_policy_mismatch")
            raw_discovery=Path(workflow.get("discovery_report",""))
            if raw_discovery.is_symlink(): raise ValueError("discovery_symlink")
            discovery_path=raw_discovery.resolve(strict=True)
            if (discovery_path.parent!=self.base.resolve() or not discovery_path.name.startswith("DISCOVERY_")
                    or discovery_path.stat().st_size>self.MAX_DIGEST_BYTES
                    or hashlib.sha256(discovery_path.read_bytes()).hexdigest()!=workflow.get("discovery_report_sha256")):
                raise ValueError("discovery_report_mismatch")
            discovery=json.loads(discovery_path.read_text(encoding="utf-8"))
            expected=discovery.get("candidates",[])[:len(workflow.get("selected_candidates",[]))]
            expected_rows=[{key:row.get(key) for key in
                ("rank","name","url","score","discovery_score","relevance_score","stars","language","license")}
                for row in expected]
            if (discovery.get("query")!=objective or not expected_rows
                    or workflow.get("selected_candidates")!=expected_rows
                    or len({row.get("url") for row in expected_rows})!=len(expected_rows)):
                raise ValueError("automatic_candidate_selection_mismatch")
            raw_analysis=Path(workflow.get("analysis_report",""))
            if raw_analysis.is_symlink(): raise ValueError("analysis_report_symlink")
            analysis_path=raw_analysis.resolve(strict=True)
            if (analysis_path.parent!=self.base.resolve()
                    or not (analysis_path.name.startswith("DIGEST_") or analysis_path.name.startswith("MULTI_DIGEST_"))
                    or analysis_path!=Path(result.get("report","")).resolve(strict=True)
                    or hashlib.sha256(analysis_path.read_bytes()).hexdigest()!=workflow.get("analysis_report_sha256")):
                raise ValueError("analysis_report_mismatch")
            if workflow.get("analysis_type")=="multi_source":
                report=json.loads(analysis_path.read_text(encoding="utf-8")); rows=report.get("sources",[])
                if [row.get("source") for row in rows]!=[row.get("url") for row in expected_rows]:
                    raise ValueError("selected_candidates_do_not_match_analysis_sources")
                verification={"status":"analyzed","job_id":report.get("job_id"),"report":str(analysis_path),
                    "source_count":report.get("source_count"),"combined_tree_sha256":report.get("combined_tree_sha256"),
                    "capability_candidates":report.get("capability_comparison",{}).get("candidates"),
                    "license_comparison":report.get("license_comparison"),
                    "source_quality_comparison":report.get("source_quality_comparison"),
                    "security":{"source_threat_counts":[row.get("security",{}).get("threat_count",0) for row in rows]},
                    "policy":report.get("policy")}
                verified=self.verify_multi_postcondition({"sources":[row["source"] for row in rows]},verification)
            elif workflow.get("analysis_type")=="single_source":
                report=json.loads(analysis_path.read_text(encoding="utf-8"))
                if report.get("source")!=(expected_rows[0].get("url") if expected_rows else None):
                    raise ValueError("selected_candidate_does_not_match_analysis_source")
                verification={"status":"digested","source":report.get("source"),"report":str(analysis_path),
                    "tree_sha256":report.get("tree_sha256"),"security":report.get("security"),
                    "license":report.get("license"),"capabilities":report.get("capability_candidates"),
                    "alice_capability_assessment":report.get("alice_capability_assessment")}
                verified=self.verify_single_postcondition({"source":report.get("source")},verification)
            else:
                raise ValueError("objective_analysis_type_invalid")
            if not verified.ok: raise ValueError("objective_analysis_postcondition_failed")
            return PostconditionResult(True,{"observed":True,
                "workflow_sha256":hashlib.sha256(workflow_path.read_bytes()).hexdigest(),
                "discovery_sha256":workflow["discovery_report_sha256"],
                "analysis_report_sha256":workflow["analysis_report_sha256"],
                "automatic_selection_rechecked":True,"analysis_rechecked":True},
                "objective discovery, automatic selection, and quarantine analysis read back")
        except Exception as exc:
            return PostconditionResult(False,{"observed":False},
                f"objective_postcondition_failed:{type(exc).__name__}")

    @staticmethod
    def _multi_source_identity(source):
        raw=str(source).strip()
        if not raw:
            raise DevourError("Every multi-source DEVOUR input must be a non-empty path or URL.")
        if raw.lower().startswith(("http://","https://")):
            owner,repo=AssimilationEngine._repo_slug(raw)
            return f"https://github.com/{owner.casefold()}/{repo.casefold()}", f"{owner}/{repo}"
        try:
            resolved=Path(raw).expanduser().resolve(strict=False)
        except (OSError,RuntimeError,ValueError) as exc:
            raise DevourError("A local DEVOUR source path could not be normalized.") from exc
        return os.path.normcase(str(resolved)), resolved.name or str(resolved)

    @staticmethod
    def _combined_source_digest(rows):
        payload="ALICE-DEVOUR-MULTI-v1\0"+"\0".join(row["tree_sha256"] for row in rows)
        return hashlib.sha256(payload.encode("ascii")).hexdigest()

    @staticmethod
    def _archive_revision(acquired, is_url):
        if not is_url:
            return None
        match=re.search(r"-([0-9a-f]{7,40})$",Path(acquired).name,re.IGNORECASE)
        return match.group(1).lower() if match else None

    @staticmethod
    def _quality_evidence(inventory,analysis,security,license_info):
        project=analysis.get("project",{}) if isinstance(analysis,dict) else {}
        if not isinstance(project,dict): project={}
        manifests=project.get("manifests",[]) if isinstance(project.get("manifests",[]),list) else []
        dependencies=project.get("dependencies",[]) if isinstance(project.get("dependencies",[]),list) else []
        modules=analysis.get("modules",[]) if isinstance(analysis,dict) else []
        tests=project.get("test_files",[]) if isinstance(project.get("test_files",[]),list) else []
        if not tests:
            tests=analysis.get("tests",[]) if isinstance(analysis,dict) else []
        systems=project.get("build_systems",[]) if isinstance(project.get("build_systems",[]),list) else []
        language_counts={}
        for module in modules:
            if isinstance(module,dict):
                lang=str(module.get("language","unknown"))[:40]
                language_counts[lang]=language_counts.get(lang,0)+1
        parsed=sum(row.get("status")=="parsed" for row in manifests if isinstance(row,dict))
        error_paths={str(row.get("path","")) for row in project.get("parse_errors",[])
            if isinstance(row,dict)}
        error_paths.update(str(row.get("path","")) for row in manifests if isinstance(row,dict)
            and row.get("status") in {"parse_error","unsupported_parser","too_large"})
        errors=len(error_paths)
        normalized_deps=[]
        for row in dependencies:
            if not isinstance(row,dict): continue
            normalized_deps.append({"ecosystem":str(row.get("ecosystem","unknown"))[:40],
                "name":str(row.get("name",""))[:200],
                "specification":str(row.get("specification",""))[:300],
                "scope":str(row.get("scope","runtime"))[:40]})
        normalized_deps.sort(key=lambda row:(row["ecosystem"].casefold(),row["name"].casefold(),
                                             row["scope"].casefold(),row["specification"]))
        constraints=[]
        for manifest in manifests:
            if not isinstance(manifest,dict): continue
            values=manifest.get("project",{})
            if isinstance(values,dict) and values.get("requires-python"):
                constraints.append({"manifest":str(manifest.get("path",""))[:300],
                    "requires_python":str(values["requires-python"])[:120]})
        license_kind=str((license_info or {}).get("kind","Unknown"))
        license_review=license_requires_review(license_kind)
        modules_count=len(modules); test_count=len(tests); threat_count=int((security or {}).get("threat_count",0))
        score=(20 if test_count else 0)+(15 if modules_count else 0)+(15 if parsed else 0)
        score+=(20 if errors==0 and manifests else 0)+(20 if threat_count==0 else 0)+(10 if not license_review else 0)
        return {"file_count":int(inventory.get("file_count",0)),"total_bytes":int(inventory.get("total_bytes",0)),
            "module_count":modules_count,"module_languages":dict(sorted(language_counts.items())),
            "test_file_count":test_count,"tests_present":bool(test_count),
            "manifest_count":len(manifests),"parsed_manifest_count":parsed,"manifest_parse_error_count":errors,
            "dependency_count":len(normalized_deps),"dependencies":normalized_deps[:100],
            "dependency_list_truncated":len(normalized_deps)>100,
            "build_systems":sorted(str(item)[:100] for item in systems),
            "declared_python_constraints":constraints[:100],
            "license_kind":license_kind,"license_review_required":license_review,
            "static_security_threat_count":threat_count,"static_quality_score":min(100,score),
            "score_components":{"tests_present":20 if test_count else 0,
                "source_modules_present":15 if modules_count else 0,"parsed_manifest_present":15 if parsed else 0,
                "manifest_parse_clean":20 if errors==0 and manifests else 0,
                "no_static_findings":20 if threat_count==0 else 0,
                "license_identified_for_review":10 if not license_review else 0}}

    @staticmethod
    def _quality_comparison(rows):
        per_source=[]; dependency_sets=[]; versions={}; dependency_union={}
        for row in rows:
            quality=row.get("source_quality",{})
            dependencies=quality.get("dependencies",[]) if isinstance(quality,dict) else []
            current=set()
            for dep in dependencies:
                if not isinstance(dep,dict) or not dep.get("name"): continue
                identity=(str(dep.get("ecosystem","unknown")).casefold(),str(dep["name"]).casefold())
                spec=str(dep.get("specification",""))
                current.add((identity[0],identity[1],spec))
                dependency_union[(identity[0],identity[1],spec)]=dep
                versions.setdefault(identity,set()).add(spec)
            dependency_sets.append(current)
            per_source.append({"source_index":row.get("source_index"),"source_label":row.get("source_label"),
                "source_revision":row.get("source_revision"),"tree_sha256":row.get("tree_sha256"),
                "quality":quality})
        common=set.intersection(*dependency_sets) if dependency_sets else set()
        conflicts=[{"ecosystem":key[0],"name":key[1],"specifications":sorted(specs)}
            for key,specs in sorted(versions.items()) if len(specs)>1]
        union=[dependency_union[key] for key in sorted(dependency_union)]
        return {"per_source":per_source,"dependency_comparison":{
                "union":union[:500],"union_truncated":len(union)>500,
                "common_to_all_sources":[dependency_union[key] for key in sorted(common)[:500]],
                "conflicting_specifications":conflicts[:200],"conflicts_truncated":len(conflicts)>200},
            "compatibility_comparison":{"per_source":[{"source_index":row.get("source_index"),
                "source_label":row.get("source_label"),"module_languages":row.get("source_quality",{}).get("module_languages",{}),
                "build_systems":row.get("source_quality",{}).get("build_systems",[]),
                "declared_python_constraints":row.get("source_quality",{}).get("declared_python_constraints",[]),
                "assessment":"static signals only; ALICE-native reimplementation and dependency review required"}
                for row in rows],"external_code_executed":False,
                "policy":"No imported source or dependency is installed or executed during compatibility analysis"}}

    @staticmethod
    def _write_json(path, value):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

    def devour_many(self, sources):
        """Analyze 2-8 untrusted sources together, without execution or promotion."""
        if isinstance(sources,(str,bytes)) or not isinstance(sources,(list,tuple)):
            raise DevourError("Provide a list of 2 to 8 local paths or public GitHub URLs.")
        if not 2<=len(sources)<=self.MAX_MULTI_SOURCES:
            raise DevourError(f"Multi-source DEVOUR requires 2 to {self.MAX_MULTI_SOURCES} inputs.")

        normalized=[]
        seen=set()
        for raw in sources:
            identity,label=self._multi_source_identity(raw)
            key=identity.casefold()
            if key in seen:
                raise DevourError("Duplicate sources are not allowed in one multi-source DEVOUR job.")
            seen.add(key)
            normalized.append({"input":str(raw).strip(),"identity":identity,"label":label})

        source_signature="\n".join(row["identity"] for row in normalized)
        stamp=(time.strftime("%Y%m%d_%H%M%S")+"_"+str(time.time_ns())+"_"+
               hashlib.sha256(source_signature.encode("utf-8")).hexdigest()[:8])
        job=self.base/("job_multi_"+stamp)
        job.mkdir(parents=True,exist_ok=False)
        report_path=self.base/("MULTI_DIGEST_"+stamp+".json")
        per_source_byte_limit=max(1,min(self.gluttony.MAX_TOTAL_BYTES,
                                        self.MAX_MULTI_TOTAL_BYTES//len(normalized)))
        per_source_file_limit=max(1,min(self.gluttony.MAX_FILES,
                                        self.MAX_MULTI_FILES//len(normalized)))
        rows=[]
        try:
            self.gluttony.audit.append("gluttony.multi_devour_started",job_id=stamp,
                                      source_count=len(normalized),
                                      source_identities=[row["identity"] for row in normalized])
            for index,item in enumerate(normalized,1):
                slot=job/f"source_{index:02d}"
                slot.mkdir(parents=True,exist_ok=False)
                raw=item["input"]
                is_url=raw.lower().startswith(("http://","https://"))
                if is_url:
                    acquired,acquisition=self.gluttony._acquire(
                        raw,slot,max_bytes=per_source_byte_limit,max_files=per_source_file_limit)
                    owner,repo=self.gluttony._repo_slug(raw)
                    label=f"{owner}/{repo}"
                else:
                    intake=LocalInputAdapter(max_files=per_source_file_limit,
                                             max_total_bytes=per_source_byte_limit)
                    acquired,acquisition=self._copy_local(raw,slot,intake=intake)
                    label=item["label"]
                revision=self._archive_revision(acquired,is_url)
                if revision:
                    acquisition={**acquisition,"archive_revision":revision}

                security=self.gluttony.guard.scan_tree(acquired)
                inventory=self.gluttony._inventory(acquired)
                analysis=self.gluttony._analyze(acquired,inventory)
                license_info=self.gluttony._license(acquired)
                capabilities=self.gluttony._capabilities(acquired,inventory,analysis)
                tree_digest=self.gluttony.guard.digest_tree(acquired)
                snippets=self._sample_source(acquired,inventory)
                plan,assessment=self._capability_plan(capabilities,analysis,license_info)
                source_quality=self._quality_evidence(inventory,analysis,security,license_info)
                source_report={
                    "status":"analyzed","job_id":stamp,"source_index":index,
                    "source":raw,"source_identity":item["identity"],"source_label":label,
                    "source_revision":revision,
                    "quarantine":str(slot),"acquired_source":str(acquired),
                    "tree_sha256":tree_digest,"acquisition":acquisition,
                    "license":license_info,"security":security,
                    "inventory":{k:v for k,v in inventory.items() if k!="files"},
                    "architecture":analysis,"capability_candidates":capabilities,
                    "source_quality":source_quality,
                    "alice_capability_assessment":assessment,
                    "reimplementation_plan":plan,"source_samples":snippets,
                    "policy":{"executed_external_code":False,"activated_external_code":False,
                              "native_reimplementation_required":True,
                              "promotion_enabled":False,"auto_upgrade_enabled":False},
                }
                child_report=slot/"analysis_report.json"
                self._write_json(child_report,source_report)
                rows.append({
                    "source_index":index,"source":raw,"source_identity":item["identity"],
                    "source_label":label,"source_revision":revision,"quarantine":str(slot),
                    "acquired_source":str(acquired),"report":str(child_report),
                    "tree_sha256":tree_digest,"file_count":inventory["file_count"],
                    "total_bytes":inventory["total_bytes"],"license":license_info,
                    "security":security,"capability_candidates":capabilities,
                    "source_quality":source_quality,
                })

            combined=self._combined_source_digest(rows)
            candidate_map={}
            for row in rows:
                for candidate in row["capability_candidates"]:
                    name=candidate["name"]
                    item=candidate_map.setdefault(name,{"name":name,"sources":[],
                        "approval":{"status":"pending_capability_by_capability_review","approved":False}})
                    item["sources"].append({"source_index":row["source_index"],
                                            "source_label":row["source_label"],
                                            "evidence_score":candidate.get("evidence_score",0),
                                            "evidence_terms":candidate.get("evidence_terms",[]),
                                            "evidence_files":candidate.get("evidence_files",[])})
            all_names=[set(candidate["name"] for candidate in row["capability_candidates"])
                       for row in rows]
            common=sorted(set.intersection(*all_names)) if all_names else []
            license_kinds=sorted({row["license"]["kind"] for row in rows})
            trees={}
            for row in rows:
                trees.setdefault(row["tree_sha256"],[]).append({
                    "source_index":row["source_index"],"source_label":row["source_label"],
                    "source_revision":row.get("source_revision")})
            report={
                "status":"analyzed","job_type":"multi_source_devour","job_id":stamp,
                "created_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
                "source_count":len(rows),"sources":rows,
                "combined_tree_sha256":combined,
                "provenance_comparison":{"per_source":[{
                    "source_index":row["source_index"],"source_identity":row["source_identity"],
                    "source_revision":row.get("source_revision"),
                    "tree_sha256":row["tree_sha256"]} for row in rows],
                    "identical_tree_groups":[{"tree_sha256":digest,"sources":members}
                        for digest,members in sorted(trees.items()) if len(members)>1]},
                "capability_comparison":{"common_to_all_sources":common,
                    "candidate_union":sorted(candidate_map),
                    "candidates":list(candidate_map.values())},
                "license_comparison":{"consistent_detected_license":len(license_kinds)==1,
                    "detected_license_kinds":license_kinds,
                    "per_source":[{"source_index":row["source_index"],
                                   "source_label":row["source_label"],"license":row["license"]}
                                  for row in rows]},
                "source_quality_comparison":self._quality_comparison(rows),
                "policy":{"executed_external_code":False,"activated_external_code":False,
                    "promotion_enabled":False,"auto_upgrade_enabled":False,
                    "native_reimplementation_required":True,
                    "capability_approval":"required_individually_before_reimplementation_or_promotion"},
            }
            self._write_json(report_path,report)
            self.gluttony.audit.append("gluttony.multi_devour_completed",job_id=stamp,
                                      source_count=len(rows),combined_tree_sha256=combined,
                                      capability_candidate_count=len(candidate_map))
            return {"ok":True,"status":"analyzed","job_id":stamp,"report":str(report_path),
                    "source_count":len(rows),"combined_tree_sha256":combined,
                    "capability_candidates":report["capability_comparison"]["candidates"],
                    "license_comparison":report["license_comparison"],
                    "source_quality_comparison":report["source_quality_comparison"],
                    "security":{"source_threat_counts":[row["security"].get("threat_count",0) for row in rows]},
                    "policy":report["policy"]}
        except Exception as exc:
            try:
                self.gluttony.audit.append("gluttony.multi_devour_failed",job_id=stamp,
                                          completed_source_count=len(rows),failure_type=type(exc).__name__)
            except Exception:
                pass
            failed={"status":"failed","job_type":"multi_source_devour","job_id":stamp,
                    "source_count":len(normalized),"completed_source_count":len(rows),
                    "sources":rows,"failure_type":type(exc).__name__,
                    "policy":{"executed_external_code":False,"promotion_enabled":False,
                              "auto_upgrade_enabled":False}}
            self._write_json(report_path,failed)
            if isinstance(exc,DevourError):
                raise
            if isinstance(exc,(IntakeError,AssimilationError)):
                raise DevourError(str(exc)) from exc
            raise

    def verify_multi_postcondition(self,args,result):
        """Recompute multi-source DEVOUR evidence from quarantined trees and reports."""
        from ..execution.postconditions import PostconditionResult
        if not isinstance(result,dict) or result.get("status")!="analyzed":
            return PostconditionResult(False,{"observed":False},"multi_source_result_not_analyzed")
        raw_sources=args.get("sources") if isinstance(args,dict) else None
        if (not isinstance(raw_sources,(list,tuple))
                or not 2<=len(raw_sources)<=self.MAX_MULTI_SOURCES
                or len(raw_sources)!=result.get("source_count")):
            return PostconditionResult(False,{"observed":False},"multi_source_input_count_mismatch")
        try:
            expected=[self._multi_source_identity(source)[0] for source in raw_sources]
            if len(set(identity.casefold() for identity in expected))!=len(expected):
                raise ValueError("duplicate_source_identity")
            raw_report=Path(result.get("report","")).expanduser()
            if raw_report.is_symlink():
                raise ValueError("report_symlink")
            report_path=raw_report.resolve(strict=True)
            if (report_path.parent!=self.base.resolve()
                    or not report_path.name.startswith("MULTI_DIGEST_")
                    or report_path.stat().st_size>self.MAX_DIGEST_BYTES):
                raise ValueError("report_outside_devour_store")
            report=json.loads(report_path.read_text(encoding="utf-8"))
            rows=report.get("sources")
            job_id=str(report.get("job_id",""))
            if (report.get("status")!="analyzed" or report.get("job_type")!="multi_source_devour"
                    or report.get("job_id")!=result.get("job_id")
                    or not re.fullmatch(r"[0-9]{8}_[0-9]{6}_[0-9]+_[0-9a-f]{8}",job_id)
                    or not isinstance(rows,list) or len(rows)!=len(expected)
                    or report.get("source_count")!=len(expected)):
                raise ValueError("aggregate_report_mismatch")
            job_root=report_path.parent/("job_multi_"+job_id)
            if job_root.is_symlink() or not job_root.is_dir():
                raise ValueError("quarantine_job_missing_or_symlinked")

            def security_signature(value):
                if not isinstance(value,dict) or not isinstance(value.get("findings"),list):
                    raise ValueError("security_evidence_invalid")
                findings=[]
                for finding in value["findings"]:
                    if not isinstance(finding,dict):
                        raise ValueError("security_finding_invalid")
                    findings.append((str(finding.get("type","")),str(finding.get("path","")),
                                     str(finding.get("sample",""))))
                return (int(value.get("threat_count",-1)),int(value.get("files_scanned",-1)),
                        int(value.get("symlinks_skipped",-1)),tuple(sorted(findings)))

            observed=[]; child_reports=[]; threat_counts=[]
            for index,(row,identity) in enumerate(zip(rows,expected),1):
                if (not isinstance(row,dict) or row.get("source_index")!=index
                        or row.get("source_identity")!=identity):
                    raise ValueError("source_identity_mismatch")
                raw_slot=Path(row.get("quarantine","")).expanduser()
                raw_acquired=Path(row.get("acquired_source","")).expanduser()
                raw_child=Path(row.get("report","")).expanduser()
                if raw_slot.is_symlink() or raw_child.is_symlink():
                    raise ValueError("source_artifact_symlink")
                slot=raw_slot.resolve(strict=True); acquired=raw_acquired.resolve(strict=True)
                child_report=raw_child.resolve(strict=True)
                expected_slot=(job_root/f"source_{index:02d}").resolve()
                if (slot!=expected_slot or acquired!=slot and slot not in acquired.parents
                        or child_report!=slot.joinpath("analysis_report.json")
                        or child_report.stat().st_size>self.MAX_DIGEST_BYTES):
                    raise ValueError("source_artifact_outside_quarantine")
                if any(path.is_symlink() for path in slot.rglob("*")):
                    raise ValueError("quarantine_contains_symlink")
                child=json.loads(child_report.read_text(encoding="utf-8"))
                actual=self.gluttony.guard.digest_tree(acquired)
                if (child.get("status")!="analyzed" or child.get("job_id")!=job_id
                        or child.get("source_index")!=index or child.get("source")!=row.get("source")
                        or child.get("source_identity")!=identity
                        or child.get("source_label")!=row.get("source_label")
                        or child.get("source_revision")!=row.get("source_revision")
                        or child.get("quarantine")!=str(slot)
                        or child.get("acquired_source")!=str(acquired)
                        or child.get("tree_sha256")!=row.get("tree_sha256")
                        or actual!=row.get("tree_sha256")):
                    raise ValueError("source_tree_or_report_mismatch")
                child_policy=child.get("policy")
                if (not isinstance(child_policy,dict)
                        or child_policy.get("executed_external_code") is not False
                        or child_policy.get("activated_external_code") is not False
                        or child_policy.get("promotion_enabled") is not False
                        or child_policy.get("auto_upgrade_enabled") is not False
                        or child_policy.get("native_reimplementation_required") is not True):
                    raise ValueError("source_policy_mismatch")

                # Re-run bounded static observers so edited summaries cannot pass by
                # remaining internally consistent with an edited aggregate report.
                fresh_security=self.gluttony.guard.scan_tree(acquired)
                fresh_inventory=self.gluttony._inventory(acquired)
                fresh_analysis=self.gluttony._analyze(acquired,fresh_inventory)
                fresh_license=self.gluttony._license(acquired)
                fresh_candidates=self.gluttony._capabilities(acquired,fresh_inventory,fresh_analysis)
                fresh_samples=self._sample_source(acquired,fresh_inventory)
                fresh_inventory_summary={key:value for key,value in fresh_inventory.items() if key!="files"}
                fresh_quality=self._quality_evidence(fresh_inventory,fresh_analysis,fresh_security,fresh_license)
                if (security_signature(row.get("security"))!=security_signature(fresh_security)
                        or security_signature(child.get("security"))!=security_signature(fresh_security)
                        or row.get("license")!=fresh_license or child.get("license")!=fresh_license
                        or row.get("file_count")!=fresh_inventory["file_count"]
                        or row.get("total_bytes")!=fresh_inventory["total_bytes"]
                        or child.get("inventory")!=fresh_inventory_summary
                        or child.get("architecture")!=fresh_analysis
                        or row.get("capability_candidates")!=fresh_candidates
                        or child.get("capability_candidates")!=fresh_candidates
                        or row.get("source_quality")!=fresh_quality
                        or child.get("source_quality")!=fresh_quality
                        or child.get("source_samples")!=fresh_samples):
                    raise ValueError("source_analysis_summary_mismatch")
                observed.append(row); child_reports.append(child)
                threat_counts.append(fresh_security["threat_count"])

            digest=self._combined_source_digest(observed)
            policy=report.get("policy")
            if (digest!=report.get("combined_tree_sha256")
                    or digest!=result.get("combined_tree_sha256")
                    or not isinstance(policy,dict)
                    or policy.get("executed_external_code") is not False
                    or policy.get("activated_external_code") is not False
                    or policy.get("promotion_enabled") is not False
                    or policy.get("auto_upgrade_enabled") is not False
                    or policy.get("native_reimplementation_required") is not True
                    or policy.get("capability_approval")!="required_individually_before_reimplementation_or_promotion"):
                raise ValueError("aggregate_digest_or_policy_mismatch")

            provenance=[{"source_index":row["source_index"],"source_identity":row["source_identity"],
                         "source_revision":row.get("source_revision"),"tree_sha256":row["tree_sha256"]}
                        for row in observed]
            trees={}
            for row in observed:
                trees.setdefault(row["tree_sha256"],[]).append({
                    "source_index":row["source_index"],"source_label":row["source_label"],
                    "source_revision":row.get("source_revision")})
            identical=[{"tree_sha256":tree,"sources":members}
                       for tree,members in sorted(trees.items()) if len(members)>1]
            if report.get("provenance_comparison")!={"per_source":provenance,"identical_tree_groups":identical}:
                raise ValueError("provenance_comparison_mismatch")

            candidate_map={}
            for row in observed:
                for candidate in row["capability_candidates"]:
                    item=candidate_map.setdefault(candidate["name"],{"name":candidate["name"],"sources":[],
                        "approval":{"status":"pending_capability_by_capability_review","approved":False}})
                    item["sources"].append({"source_index":row["source_index"],
                        "source_label":row["source_label"],"evidence_score":candidate.get("evidence_score",0),
                        "evidence_terms":candidate.get("evidence_terms",[]),
                        "evidence_files":candidate.get("evidence_files",[])})
            candidate_rows=list(candidate_map.values()); candidate_names=sorted(candidate_map)
            common=sorted(set.intersection(*[
                {candidate["name"] for candidate in row["capability_candidates"]} for row in observed
            ]))
            comparison={"common_to_all_sources":common,"candidate_union":candidate_names,
                        "candidates":candidate_rows}
            license_kinds=sorted({row["license"]["kind"] for row in observed})
            license_comparison={"consistent_detected_license":len(license_kinds)==1,
                "detected_license_kinds":license_kinds,
                "per_source":[{"source_index":row["source_index"],"source_label":row["source_label"],
                               "license":row["license"]} for row in observed]}
            quality_comparison=self._quality_comparison(observed)
            if (report.get("capability_comparison")!=comparison
                    or report.get("license_comparison")!=license_comparison
                    or report.get("source_quality_comparison")!=quality_comparison):
                raise ValueError("aggregate_capability_or_license_comparison_mismatch")
            if (result.get("capability_candidates")!=candidate_rows
                    or result.get("license_comparison")!=license_comparison
                    or result.get("source_quality_comparison")!=quality_comparison
                    or result.get("security")!={"source_threat_counts":threat_counts}
                    or result.get("policy")!=policy):
                raise ValueError("runtime_result_does_not_match_persisted_report")
            return PostconditionResult(True,{"observed":True,"report":str(report_path),
                "source_count":len(rows),"combined_tree_sha256":digest,
                "quarantined_sources_rehashed":True,"security_summaries_recomputed":True,
                "analysis_summaries_recomputed":True,
                "capability_license_and_provenance_comparisons_recomputed":True},
                "aggregate report and source evidence read back")
        except Exception as exc:
            return PostconditionResult(False,{"observed":False},f"multi_source_postcondition_failed:{type(exc).__name__}")
