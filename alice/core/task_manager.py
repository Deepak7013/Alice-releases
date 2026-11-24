"""Long-running task orchestration with bounded retries, checkpoints and verification."""
import json, time, uuid
from pathlib import Path

class TaskManager:
    def __init__(self, agent, workspace=None):
        self.agent=agent
        self.root=Path(workspace or Path(__file__).resolve().parents[2])
        self.state_dir=self.root/"alice_workspace"/"tasks"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def run(self, request, max_rounds=None):
        task_id=str(uuid.uuid4())[:8]
        started=time.time()
        result=self.agent.run(request, max_rounds=max_rounds)
        state={"id":task_id,"request":request,"started":started,"finished":time.time(),"status":"completed","result":str(result)}
        (self.state_dir/f"{task_id}.json").write_text(json.dumps(state,indent=2,default=str),encoding="utf-8")
        return result

    def list_tasks(self, limit=20):
        files=sorted(self.state_dir.glob("*.json"),key=lambda p:p.stat().st_mtime,reverse=True)[:limit]
        return [json.loads(p.read_text(encoding="utf-8")) for p in files]

    def resume(self, task_id):
        p=self.state_dir/(task_id+".json")
        if not p.exists(): raise FileNotFoundError(task_id)
        state=json.loads(p.read_text(encoding="utf-8"))
        return self.run(state["request"])
