"""ALICE Gluttony: safe repository assimilation and capability analysis.

This subsystem treats external repositories as untrusted source material.
It downloads bounded archives into a quarantine area, performs static analysis, records
license/provenance, and produces an ALICE-native capability plan. It never
imports or executes code from the acquired project during assimilation.
"""
from __future__ import annotations
import hashlib, json, re, time, urllib.parse, urllib.request
from pathlib import Path
from ..security.audit_chain import AuditChain
from ..security.ingest_guard import IngestGuard
from .project_analyzer import ProjectManifestAnalyzer
from .intake import IntakeError, LocalInputAdapter

class AssimilationError(RuntimeError):
    pass


def license_requires_review(kind):
    value = str(kind or "Unknown").strip()
    folded = value.casefold()
    family = value.upper().split("-", 1)[0].split(" ", 1)[0]
    return (not value or folded.startswith("no license") or "manual review" in folded
            or family in {"GPL", "AGPL", "LGPL", "MPL"})

class AssimilationEngine:
    MAX_FILES = 12000
    MAX_FILE_BYTES = 2_000_000
    MAX_TOTAL_BYTES = 250_000_000
    CODE_EXTENSIONS = {".py",".pyi",".rs",".toml",".js",".ts",".tsx",".jsx",".go",".java",".kt",".c",".h",".cpp",".hpp",".cs",".rb",".php",".swift",".md",".rst",".txt",".json",".yaml",".yml",".sh",".ps1",".bat",".dart",".lua",".scala",".sc",".pl",".r",".jl",".ex",".exs",".hs",".lhs",".clj",".cljs",".cljc",".vue",".svelte",".proto",".graphql",".gql",".gradle",".kts",".properties",".ipynb",".html",".css",".scss",".sass",".less"}
    def __init__(self, root=None):
        self.root=Path(root or Path(__file__).resolve().parents[2]).resolve()
        self.base=self.root/"alice_workspace"/"gluttony"
        self.quarantine=self.base/"quarantine"
        self.reports=self.base/"reports"
        self.capabilities=self.base/"capabilities"
        for p in (self.quarantine,self.reports,self.capabilities): p.mkdir(parents=True,exist_ok=True)
        self.guard=IngestGuard()
        self.audit=AuditChain(self.root/"alice_workspace"/"runtime"/"security_audit.jsonl")
        self.project_analyzer=ProjectManifestAnalyzer()

    @staticmethod
    def _repo_slug(url):
        parsed=urllib.parse.urlparse(url)
        if parsed.scheme not in {"http","https"} or parsed.netloc.lower()!="github.com":
            raise AssimilationError("Only public HTTPS GitHub repositories are supported by the URL importer.")
        parts=[p for p in parsed.path.strip("/").split("/") if p]
        if len(parts)<2: raise AssimilationError("Use a GitHub repository URL such as https://github.com/owner/repo")
        owner,repos=parts[0],parts[1]
        repo=repos[:-4] if repos.endswith(".git") else repos
        if (owner in {".",".."} or repo in {".",".."}
                or not re.fullmatch(r"[A-Za-z0-9_.-]+",owner)
                or not re.fullmatch(r"[A-Za-z0-9_.-]+",repo)):
            raise AssimilationError("Invalid GitHub repository name.")
        return owner,repo

    def _download_zip(self,url,dest,*,max_bytes=None,max_files=None):
        owner,repo=self._repo_slug(url)
        byte_limit=min(self.MAX_TOTAL_BYTES,int(max_bytes or self.MAX_TOTAL_BYTES))
        file_limit=min(self.MAX_FILES,int(max_files or self.MAX_FILES))
        archive_url=("https://api.github.com/repos/"+
                     urllib.parse.quote(owner,safe="")+"/"+
                     urllib.parse.quote(repo,safe="")+"/zipball")
        req=urllib.request.Request(archive_url,headers={"User-Agent":"ALICE-DEVOUR","Accept":"application/vnd.github+json"})
        archive=dest/"repo.zip"
        try:
            with urllib.request.urlopen(req,timeout=60) as response:
                final_url=urllib.parse.urlparse(response.geturl())
                if final_url.scheme!="https" or final_url.hostname not in {"api.github.com","github.com","codeload.github.com"}:
                    raise AssimilationError("GitHub archive redirected to an untrusted host.")
                length=response.headers.get("Content-Length")
                if length and int(length)>byte_limit:
                    raise AssimilationError("Repository archive exceeds ALICE's quarantine size limit.")
                total=0
                with archive.open("wb") as output:
                    while True:
                        block=response.read(1024*1024)
                        if not block: break
                        total+=len(block)
                        if total>byte_limit:
                            raise AssimilationError("Repository archive exceeds ALICE's quarantine size limit.")
                        output.write(block)
            staged=LocalInputAdapter(max_files=file_limit,max_total_bytes=byte_limit).stage(archive,dest)
        except IntakeError as exc:
            raise AssimilationError(str(exc)) from exc
        finally:
            archive.unlink(missing_ok=True)
        roots=[p for p in staged.source.iterdir() if p.is_dir()]
        return roots[0] if len(roots)==1 else staged.source

    def _acquire(self,url,work,*,max_bytes=None,max_files=None):
        owner,repo=self._repo_slug(url)
        if max_bytes is None and max_files is None:
            acquired=self._download_zip(url,work)
        else:
            acquired=self._download_zip(url,work,max_bytes=max_bytes,max_files=max_files)
        return acquired,{"method":"archive","owner":owner,"repo":repo}

    def _license(self,source):
        names={"license","license.txt","license.md","copying","copying.txt"}
        source=Path(source)
        roots=[source]
        try:
            direct=[p for p in source.iterdir() if p.name.casefold() in names and p.is_file() and not p.is_symlink()]
            children=[p for p in source.iterdir() if p.is_dir() and not p.is_symlink()]
            # Archive intake often preserves one repository root directory.
            # Inspect that root only when the staging directory has no direct
            # license file, avoiding accidental attribution of vendored licenses.
            if not direct and len(children)==1:
                roots.append(children[0])
        except Exception:
            pass
        license_paths=[]
        for root in roots:
            try:
                for path in root.iterdir():
                    if path.name.casefold() in names and path.is_file() and not path.is_symlink():
                        license_paths.append(path)
            except Exception:
                continue
        found=sorted(path.relative_to(source).as_posix() for path in license_paths)
        text=""
        for path in license_paths:
            try:text += "\n"+path.read_text(errors="replace")[:12000]
            except Exception: pass
        low=text.lower()
        if "mit license" in low: kind="MIT"
        elif "apache license" in low: kind="Apache-2.0"
        elif "mozilla public license" in low: kind="MPL"
        elif "gnu affero general public license" in low: kind="AGPL"
        elif "gnu lesser general public license" in low or "gnu library general public license" in low: kind="LGPL"
        elif "gnu general public license" in low:
            version=re.search(r"\bversion\s+([23])\b",low)
            kind="GPL-"+version.group(1)+".0" if version else "GPL"
        elif found: kind="Declared (manual review required)"
        else: kind="No license file detected (manual review required)"
        return {"kind":kind,"files":found}

    def _inventory(self,source):
        files=[]; total=0; ext_counts={}
        for p in sorted(source.rglob("*")):
            if p.is_symlink() or not p.is_file() or ".git" in p.parts: continue
            rel=p.relative_to(source).as_posix()
            size=p.stat().st_size; total+=size
            if len(files)>=self.MAX_FILES: raise AssimilationError("Repository contains too many files for one assimilation pass.")
            ext=p.suffix.lower()
            with p.open("rb") as stream:
                prefix=stream.read(8192)
            digest=hashlib.sha256()
            with p.open("rb") as stream:
                for block in iter(lambda:stream.read(1024*1024),b""):
                    digest.update(block)
            if size>self.MAX_FILE_BYTES:
                parser="metadata_only_size_limit"
            elif ext==".class":
                parser="java_bytecode_static" if prefix.startswith(b"\xca\xfe\xba\xbe") else "metadata_only_unrecognized_binary"
            elif ext in {".docx",".xlsx",".pptx",".odt",".ods",".odp",".pdf"}:
                parser="metadata_only_document_adapter_unavailable"
            elif b"\x00" in prefix:
                parser="metadata_only_binary"
            elif ext in self.CODE_EXTENSIONS:
                parser="static_source_candidate"
            else:
                parser="metadata_only_no_content_adapter"
            files.append({"path":rel,"size":size,"ext":ext,"sha256":digest.hexdigest(),"parser":parser})
            ext_counts[ext or "[none]"]=ext_counts.get(ext or "[none]",0)+1
        if total>self.MAX_TOTAL_BYTES: raise AssimilationError("Repository exceeds total quarantine size limit.")
        return {"file_count":len(files),"total_bytes":total,"extensions":dict(sorted(ext_counts.items(),key=lambda x:-x[1])),"files":files}

    def _analyze(self,source,inventory):
        modules=[]; entrypoints=[]; dependencies=[]; tests=[]
        file_catalog=[{key:item.get(key) for key in ("path","size","ext","sha256","parser")}
                      for item in inventory["files"]]
        symbol_patterns={
            ".py":re.compile(r"(?m)^\s*(async\s+def|def|class)\s+([A-Za-z_]\w*)"),
            ".pyi":re.compile(r"(?m)^\s*(async\s+def|def|class)\s+([A-Za-z_]\w*)"),
            ".rs":re.compile(r"(?m)^\s*(?:pub(?:\([^)]*\))?\s+)?(fn|struct|enum|trait|type|const|static)\s+([A-Za-z_]\w*)"),
            ".go":re.compile(r"(?m)^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\("),
            ".java":re.compile(r"(?m)^\s*(?:(?:public|protected|private|static|final|abstract|synchronized|native|default)\s+)*(?:class|interface|enum|record)\s+([A-Za-z_$][\w$]*)|^\s*(?:(?:public|protected|private|static|final|abstract|synchronized|native|default)\s+)+[\w$<>.?\[\], ]+\s+([A-Za-z_$][\w$]*)\s*\("),
            ".js":re.compile(r"(?m)^\s*(?:export\s+)?(?:async\s+)?function\s+([\w$]+)|^\s*(?:export\s+)?class\s+([\w$]+)|^\s*(?:export\s+)?(?:const|let|var)\s+([\w$]+)\s*=\s*(?:async\s*)?(?:\([^\n]*\)|[\w$]+)\s*=>"),
            ".ts":re.compile(r"(?m)^\s*(?:export\s+)?(?:async\s+)?function\s+([\w$]+)|^\s*(?:export\s+)?(?:abstract\s+)?class\s+([\w$]+)|^\s*(?:export\s+)?interface\s+([\w$]+)|^\s*(?:export\s+)?(?:const|let|var)\s+([\w$]+)\s*=\s*(?:async\s*)?(?:\([^\n]*\)|[\w$]+)\s*=>"),
            ".rb":re.compile(r"(?m)^\s*(def|class|module)\s+([\w!?=]+)"),
            ".php":re.compile(r"(?m)^\s*(?:function|class|interface|trait)\s+([\w$]+)"),
            ".swift":re.compile(r"(?m)^\s*(func|class|struct|enum|protocol)\s+([\w$]+)"),
            ".vue":re.compile(r"(?m)^\s*(?:export\s+)?(?:async\s+)?function\s+([\w$]+)|^\s*(?:export\s+)?class\s+([\w$]+)|^\s*(?:export\s+)?(?:const|let|var)\s+([\w$]+)\s*=\s*(?:async\s*)?(?:\([^\n]*\)|[\w$]+)\s*=>"),
            ".svelte":re.compile(r"(?m)^\s*(?:export\s+)?(?:async\s+)?function\s+([\w$]+)|^\s*(?:export\s+)?(?:const|let|var)\s+([\w$]+)\s*=\s*(?:async\s*)?(?:\([^\n]*\)|[\w$]+)\s*=>"),
        }
        for item in inventory["files"]:
            p=source/item["path"]; ext=item["ext"]
            if ext==".class" and item["size"]<=self.MAX_FILE_BYTES:
                bytecode=self.project_analyzer.inspect_java_classfile(p)
                if bytecode.get("status")=="parsed":
                    modules.append({"path":item["path"],"language":"java_bytecode_static",
                        "class_name":bytecode["class_name"],"superclass":bytecode["superclass"],
                        "interfaces":bytecode["interfaces"],"fields":bytecode["fields"],
                        "methods":bytecode["methods"],"symbols":len(bytecode["methods"]),
                        "symbol_extraction":"classfile_signature_parser_no_execution"})
                continue
            if ext not in self.CODE_EXTENSIONS: continue
            try:text=p.read_text(errors="replace")
            except Exception: continue
            if ext==".py":
                imports=re.findall(r"(?m)^\s*(?:from|import)\s+([A-Za-z0-9_.-]+)",text)
                dependencies.extend(imports[:100])
                matches=symbol_patterns[ext].findall(text)
                modules.append({"path":item["path"],"language":"python","symbols":len(matches),
                    "symbol_names":[{"kind":kind.strip(),"name":name,"line":text.count(chr(10),0,m.start())+1}
                        for m in symbol_patterns[ext].finditer(text) for kind,name in [m.groups()]][:500],
                    "symbol_extraction":"static_declaration_scan"})
            elif ext==".rs":
                rust_imports=re.findall(r"(?m)^\s*(?:pub\s+)?use\s+([A-Za-z_][A-Za-z0-9_]*)\s*::",text)
                dependencies.extend(name for name in rust_imports if name not in {"std","core","alloc"})
                matches=symbol_patterns[ext].finditer(text)
                names=[{"kind":m.group(1),"name":m.group(2),"line":text.count(chr(10),0,m.start())+1}
                       for m in matches][:500]
                modules.append({"path":item["path"],"language":"rust","symbols":len(names),
                    "symbol_names":names,"symbol_extraction":"static_declaration_scan"})
            elif ext in symbol_patterns:
                pattern=symbol_patterns[ext]
                names=[]
                for match in pattern.finditer(text):
                    groups=[value for value in match.groups() if value]
                    names.append({"kind":"declaration","name":groups[-1],
                                  "line":text.count(chr(10),0,match.start())+1})
                    if len(names)>=500: break
                if names:
                    modules.append({"path":item["path"],"language":ext.lstrip("."),
                        "symbols":len(names),"symbol_names":names,
                        "symbol_extraction":"static_declaration_heuristic"})
            if "test" in Path(item["path"]).name.lower() or "/tests/" in "/"+item["path"].lower():
                tests.append(item["path"])
            if Path(item["path"]).name.lower() in {"main.py","main.rs","__main__.py","lib.rs","src/main.rs"}:
                entrypoints.append(item["path"])
        project=self.project_analyzer.analyze(source,inventory,tests)
        parser_counts={}
        for row in file_catalog:
            key=str(row.get("parser") or "unknown")
            parser_counts[key]=parser_counts.get(key,0)+1
        return {"modules":modules[:3000],"file_catalog":file_catalog,
                "file_analysis_coverage":{"total_files":len(file_catalog),"parser_counts":dict(sorted(parser_counts.items())),
                    "external_code_executed":False,
                    "note":"Only declared static adapters are analyzed. Metadata-only entries are fingerprinted but not semantically interpreted."},
                "dependencies":sorted(set(dependencies))[:1000],"tests":tests[:1000],"entrypoints":entrypoints,"project":project}

    def _capabilities(self,source,inventory,analysis):
        text_blob=""; evidence={}
        patterns={
            "terminal_agent":("terminal","shell","command"),
            "session_management":("session","conversation","history"),
            "tool_orchestration":("tool","plugin","mcp"),
            "model_provider_abstraction":("provider","anthropic","openai","ollama"),
            "workspace_intelligence":("workspace","project","filesystem"),
            "streaming":("stream","streaming"),
            "agent_planning":("planner","plan","agent"),
            "testing_harness":("pytest","cargo test","tests"),
            "user_interface":("frontend","front-end","user interface","window","widget","theme","dashboard","component","layout","stylesheet"),
        }
        for item in inventory["files"]:
            if item["ext"] in self.CODE_EXTENSIONS and item["size"]<=250_000:
                try:content=(source/item["path"]).read_text(errors="replace")[:5000]
                except Exception: pass
                else:
                    text_blob += "\n"+content
                    low_content=content.lower()
                    for name,terms in patterns.items():
                        hits=[term for term in terms if term in low_content]
                        if hits:
                            evidence.setdefault(name,{"files":[],"terms":set()})
                            evidence[name]["files"].append(item["path"])
                            evidence[name]["terms"].update(hits)
            if len(text_blob)>1_500_000: break
        low=text_blob.lower()
        found=[]
        for name,terms in patterns.items():
            score=sum(1 for t in terms if t in low)
            if score>=max(1,len(terms)//2):
                source_evidence=evidence.get(name,{"files":[],"terms":set()})
                found.append({"name":name,"evidence_score":score,"evidence_terms":sorted(source_evidence["terms"]),
                              "evidence_files":source_evidence["files"][:20],"status":"candidate",
                              "activation":"ALICE-native reimplementation required"})
        return found

    def assimilate(self,url,learn=True):
        owner,repo=self._repo_slug(str(url).strip())
        stamp=time.strftime("%Y%m%d_%H%M%S")+"_"+hashlib.sha256(str(url).encode()).hexdigest()[:8]
        work=self.quarantine/f"{owner}_{repo}_{stamp}"
        work.mkdir(parents=True,exist_ok=False)
        self.audit.append("gluttony.acquire_started",url=url,quarantine=str(work))
        try:
            source,acq=self._acquire(url,work)
            guard=self.guard.scan_tree(source)
            inventory=self._inventory(source)
            analysis=self._analyze(source,inventory)
            license_info=self._license(source)
            caps=self._capabilities(source,inventory,analysis)
            digest=self.guard.digest_tree(source)
            report={
                "analysis_schema_version":2,
                "status":"analyzed","source_url":url,"owner":owner,"repo":repo,
                "quarantine":str(work),"tree_sha256":digest,"acquisition":acq,
                "license":license_info,"security":guard,"inventory":{k:v for k,v in inventory.items() if k!="files"},
                "architecture":analysis,"capability_candidates":caps,
                "policy":{"executed_external_code":False,"activated_external_code":False,
                          "requires_license_review":license_requires_review(license_info["kind"])}
            }
            report_path=self.reports/f"{owner}_{repo}_{stamp}.json"
            report_path.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
            capability_path=self.capabilities/f"{owner}_{repo}_{stamp}.json"
            capability_path.write_text(json.dumps({"source_url":url,"license":license_info,"capabilities":caps,"report":str(report_path)},indent=2),encoding="utf-8")
            self.audit.append("gluttony.analysis_completed",url=url,report=str(report_path),threats=guard["threat_count"],capabilities=len(caps))
            return {"ok":True,"status":"assimilated","repo":f"{owner}/{repo}","report":str(report_path),
                    "capability_registry":str(capability_path),"security":guard,"license":license_info,
                    "capabilities":caps,"message":"Repository analyzed in quarantine. No external code was imported or executed."}
        except Exception:
            self.audit.append("gluttony.analysis_failed",url=url)
            raise

    def inventory(self):
        rows=[]
        for p in sorted(self.reports.glob("*.json"),reverse=True):
            try:
                data=json.loads(p.read_text(encoding="utf-8"))
                rows.append({"repo":data.get("owner","")+"/"+data.get("repo",""),"status":data.get("status"),"report":str(p),"capabilities":len(data.get("capability_candidates",[])),"threats":data.get("security",{}).get("threat_count",0)})
            except Exception: pass
        return rows[:100]
