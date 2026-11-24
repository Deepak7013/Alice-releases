"""Goal supervisor with bounded subtasks and optional multi-agent execution."""
import json, time, uuid
class TaskState:
    PENDING="PENDING"; READY="READY"; RUNNING="RUNNING"; WAITING="WAITING"; FAILED="FAILED"; RETRYING="RETRYING"; COMPLETED="COMPLETED"; BLOCKED="BLOCKED"
class AutonomousSupervisor:
    def __init__(self, agent, multi_agent=None, world=None): self.agent=agent; self.multi_agent=multi_agent; self.world=world
    def run(self, goal, use_multi_agent=False, context=""):
        task_id=uuid.uuid4().hex[:8]; started=time.time();
        if use_multi_agent and self.multi_agent:
            result=self.multi_agent.run(goal,context=context)
        else:
            result=self.agent.run(goal)
        state={"id":task_id,"goal":goal,"state":TaskState.COMPLETED,"result":result,"started":started,"finished":time.time()}
        if self.world:self.world.update("tasks",{"id":task_id,"goal":goal,"state":state["state"]})
        return state
