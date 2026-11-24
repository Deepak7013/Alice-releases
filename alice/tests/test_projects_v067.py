from alice.projects import ProjectStore
def test_project_dependencies(tmp_path):
 s=ProjectStore(tmp_path); p=s.add_project('X'); a=s.add_task(p.project_id,'A'); b=s.add_task(p.project_id,'B',dependencies=[a.task_id]); assert b in s.blocked_tasks(p.project_id); s.set_task_status(a.task_id,'done'); assert not s.blocked_tasks(p.project_id)
def test_project_priority_validation(tmp_path):
 s=ProjectStore(tmp_path); p=s.add_project('X')
 try: s.add_task(p.project_id,'A',priority='bad'); assert False
 except ValueError: pass
