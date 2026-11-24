"""Autonomous Builder: plan, generate, test, diagnose and repair projects safely."""
import hashlib, json, re, subprocess, sys, time
from pathlib import Path

class BuilderEngine:
    def __init__(self, router, root=None, researcher=None, permission=None, test_runner=None):
        self.router=router; self.root=Path(root or Path(__file__).resolve().parents[2]).resolve()
        self.projects=(self.root/'projects_by_alice').resolve(); self.projects.mkdir(parents=True,exist_ok=True)
        self.researcher=researcher; self.permission=permission; self.test_runner=test_runner

    def _safe_project(self,name):
        name=re.sub(r'[^A-Za-z0-9_.-]+','-',name.strip()).strip('.-')[:80] or 'project'
        p=(self.projects/name).resolve()
        if self.projects not in p.parents: raise ValueError('Invalid project path')
        p.mkdir(parents=True,exist_ok=True); return p

    def _ask_json(self,prompt):
        raw=self.router.ask(prompt)
        text=raw.strip()
        if text.startswith('```'): text='\n'.join(text.splitlines()[1:-1])
        a,b=text.find('{'),text.rfind('}')
        if a<0 or b<a: raise ValueError('Builder model did not return JSON')
        return json.loads(text[a:b+1])

    def _snapshot(self,project):
        snap=project.parent/(project.name+'.alice-backup-'+time.strftime('%Y%m%d_%H%M%S'))
        if snap.exists(): return snap
        import shutil; shutil.copytree(project,snap)
        return snap

    def _files(self,project):
        out=[]
        for p in project.rglob('*'):
            if p.is_file() and '.git' not in p.parts and '__pycache__' not in p.parts:
                try: out.append({'path':str(p.relative_to(project)),'content':p.read_text(encoding='utf-8',errors='ignore')[:60000]})
                except Exception: pass
        return out

    def _write(self,project,items):
        changed=[];validated=[]
        for item in items:
            if not isinstance(item,dict): raise ValueError('Invalid project file record')
            rel=Path(item.get('path',''))
            if rel.is_absolute() or '..' in rel.parts: raise ValueError('Unsafe project path')
            candidate=project/rel
            probe=project
            for part in rel.parts:
                probe=probe/part
                if probe.is_symlink(): raise ValueError('Project output cannot traverse a symbolic link')
            p=candidate.resolve()
            if project not in p.parents and p!=project: raise ValueError('Unsafe project path')
            validated.append((rel,p,str(item.get('content',''))))
        for rel,p,content in validated:
            p.parent.mkdir(parents=True,exist_ok=True); p.write_text(content,encoding='utf-8'); changed.append(str(rel))
        return changed

    @staticmethod
    def _changed_file_receipts(project,changed):
        receipts=[]
        for value in sorted(set(changed)):
            rel=Path(value)
            candidate=project/rel;probe=project
            if rel.is_absolute() or '..' in rel.parts:
                raise ValueError('Builder output could not be safely verified')
            for part in rel.parts:
                probe=probe/part
                if probe.is_symlink(): raise ValueError('Builder output could not be safely verified')
            path=candidate.resolve()
            if project not in path.parents or not path.is_file():
                raise ValueError('Builder output could not be safely verified')
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            receipts.append({'path':rel.as_posix(),'size':path.stat().st_size,'sha256':digest})
        return receipts

    def _command_allowed(self,cmd):
        low=cmd.lower().strip()
        banned=('rm -rf','del /s /q','format ','shutdown','reg delete','diskpart','ransom','keylogger','credential','password dump','disable defender')
        return not any(x in low for x in banned)

    def _test(self,project,commands):
        results=[]
        for cmd in commands[:8]:
            if not self._command_allowed(cmd): return {'ok':False,'results':results,'error':'Unsafe test command blocked'}
            if self.test_runner is not None:
                try:
                    isolated=self.test_runner.run(project,cmd)
                    sandbox=getattr(isolated,'sandbox_evidence',{})
                    code=int(getattr(isolated,'returncode',125))
                    if not isinstance(sandbox,dict) or sandbox.get('verified') is not True:
                        code=125
                    results.append({'command':cmd,'returncode':code,
                        'stdout':str(getattr(isolated,'stdout','') or '')[-5000:],
                        'stderr':str(getattr(isolated,'stderr','') or '')[-5000:],
                        'sandbox':sandbox})
                    if code!=0:return {'ok':False,'results':results}
                except Exception as e:
                    return {'ok':False,'results':results,'error':f'Isolated test runner failed: {type(e).__name__}'}
                continue
            if self.permission:
                approval=self.permission(cmd)
                if isinstance(approval,dict): approval=approval.get('status')=='ok'
                if not approval: return {'ok':False,'results':results,'error':'Test command requires approval'}
            try:
                r=subprocess.run(cmd,shell=True,cwd=project,capture_output=True,text=True,timeout=120)
                results.append({'command':cmd,'returncode':r.returncode,'stdout':r.stdout[-5000:],'stderr':r.stderr[-5000:]})
                if r.returncode!=0: return {'ok':False,'results':results}
            except Exception as e: return {'ok':False,'results':results,'error':str(e)}
        return {'ok':True,'results':results}

    def build_ai_agent(self, request, project_name="alice-agent", research=True):
        goal = "Build a complete, maintainable AI agent/application for this goal: " + str(request) + "\n"               "Include a clear architecture, provider abstraction, tools, memory, tests, configuration, README, and safe permission boundaries. "               "It must not contain malware, credential theft, destructive behavior, persistence tricks, evasion, or security bypasses."
        return self.build(goal, project_name=project_name, research=research, max_repair_rounds=4)

    def build(self,request,project_name='alice-project',research=True,max_repair_rounds=3):
        project=self._safe_project(project_name); backup=self._snapshot(project)
        research_data=[]
        if research and self.researcher:
            try:
                q=self.router.ask('Create up to 3 concise web research queries for this build request. Return JSON {"queries":[...]}. Request: '+request)
                a,b=q.find('{'),q.rfind('}'); queries=json.loads(q[a:b+1]).get('queries',[])[:3]
                for query in queries:
                    try: research_data.append(self.researcher.search(query,4))
                    except Exception as e: research_data.append({'query':query,'error':str(e)})
            except Exception: pass
        context={'research':research_data,'files':self._files(project)}
        plan=self._ask_json('''You are Alice's autonomous software architect. Design a practical build for the user's goal. Return JSON with project_name, stack, files (path/content), tests (shell commands), and run_command. Only create normal software; no malware, credential theft, persistence, evasion, destructive actions or unauthorized access. Prefer simple maintainable technologies.\nUSER GOAL:\n'''+request+'\nCURRENT PROJECT:\n'+json.dumps(context)[:90000])
        planned_files=plan.get('files',[]);planned_tests=plan.get('tests',[])
        if (not isinstance(planned_files,list) or not planned_files
                or not isinstance(planned_tests,list) or not planned_tests or len(planned_tests)>8
                or any(not isinstance(command,str) or not command.strip() for command in planned_tests)):
            return {'ok':False,'status':'build_plan_missing_runnable_test_or_files',
                    'project':str(project),'rolled_back':False,'changed':[],'tests':{'ok':False,'results':[]}}
        changed=self._write(project,planned_files); test=self._test(project,planned_tests)
        repairs=[]
        for i in range(max_repair_rounds):
            if test.get('ok'): break
            repairs.append(test)
            files=self._files(project)
            repair=self._ask_json('''You are Alice's build repair engineer. Return JSON {"files":[{"path":"...","content":"..."}],"tests":["..."]}. Fix the failed build with the smallest reliable changes. Never add harmful behavior.\nUSER GOAL:\n'''+request+'\nFAILURE:\n'+json.dumps(test)+'\nFILES:\n'+json.dumps(files)[:90000])
            changed.extend(self._write(project,repair.get('files',[])))
            test_commands=repair.get('tests',planned_tests)
            if not isinstance(test_commands,list) or not test_commands or len(test_commands)>8 or any(not isinstance(command,str) or not command.strip() for command in test_commands):
                test={'ok':False,'results':[],'error':'Repair plan omitted runnable tests'}
                break
            test=self._test(project,test_commands)
        if not test.get('ok'):
            import shutil
            if backup.exists():
                for p in project.iterdir(): shutil.rmtree(p) if p.is_dir() else p.unlink()
                for p in backup.iterdir(): shutil.copytree(p,project/p.name) if p.is_dir() else shutil.copy2(p,project/p.name)
            return {'ok':False,'project':str(project),'rolled_back':True,'changed':changed,'tests':test,'repairs':len(repairs)}
        return {'ok':True,'project':str(project),'changed':sorted(set(changed)),'tests':test,'repairs':len(repairs),'run_command':plan.get('run_command'),'stack':plan.get('stack'),
                '_postcondition_context':{'files':self._changed_file_receipts(project,changed),
                                          'successful_test_count':len(test.get('results',[]))}}
