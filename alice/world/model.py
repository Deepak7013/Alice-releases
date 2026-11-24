from __future__ import annotations
"""Persistent local world model with freshness, provenance, confidence and conflict awareness.

The world model is an observation ledger, not a guessing engine. Current state is derived
from explicitly recorded observations and every observation carries source, timestamp,
confidence and optional TTL. Existing v3.15 APIs remain backward compatible.
"""
from pathlib import Path
from functools import wraps
import copy, json, re, threading, time, uuid

DOMAINS={"pc","browser","android","projects","tasks","environment","capabilities"}
PLANNING_DOMAIN_TERMS={
    "android":("android","phone","whatsapp","mobile device","tablet"),
    "browser":("browser","website","web page","webpage","tab","url"),
    "pc":("desktop","computer","screen","window","windows app"),
    "projects":("project","repository","repo","source code","workspace"),
    "tasks":("task","goal","schedule"),
    "environment":("environment","operating system","system status"),
    "capabilities":("capability","capabilities","tool availability"),
}

def _world_locked(method):
    @wraps(method)
    def locked(self,*args,**kwargs):
        with self._lock:
            return method(self,*args,**kwargs)
    return locked

class WorldModel:
    def __init__(self, root=None):
        self.root=Path(root or Path(__file__).resolve().parents[2]).resolve()
        self.path=self.root/"alice_workspace"/"world_state.json"
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self._lock=threading.RLock()
        self.state=self._load()

    def _load(self):
        try:
            data=json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            data={"schema":3,"updated":0,"pc":{},"browser":{},"android":{},"projects":{},"tasks":{},"environment":{},"capabilities":{},"events":[],"observations":{}}
        data.setdefault("schema",3); data["schema"]=max(3,int(data.get("schema",3))); data.setdefault("events",[]); data.setdefault("observations",{})
        for d in DOMAINS: data.setdefault(d,{})
        return data

    @_world_locked
    def _save(self):
        tmp=self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state,indent=2,ensure_ascii=False,default=str),encoding="utf-8")
        tmp.replace(self.path)

    @staticmethod
    def _confidence(value):
        try:return max(0.0,min(1.0,float(value)))
        except Exception:return 0.5

    @_world_locked
    def observe(self, domain, key, value, source="local", confidence=1.0, ttl_seconds=None, entity_id=None):
        """Record one explicit observation; never executes or infers anything."""
        if domain not in DOMAINS: raise ValueError(f"unknown world domain: {domain}")
        now=time.time(); entity=str(entity_id) if entity_id is not None else "__domain__"
        bucket=self.state.setdefault("observations",{}).setdefault(domain,{})
        bucket.setdefault(entity,{}).setdefault(str(key),[]).append({
            "value":copy.deepcopy(value),"observed_at":now,"source":str(source)[:160],
            "confidence":self._confidence(confidence),"ttl_seconds":ttl_seconds,
            "id":uuid.uuid4().hex[:12]
        })
        bucket[entity][str(key)]=bucket[entity][str(key)][-12:]
        self.state["updated"]=now
        self._event("world.observed",domain=domain,key=str(key),entity_id=entity,source=str(source)[:160])
        self._save()
        return copy.deepcopy(bucket[entity][str(key)][-1])

    def _observation_fresh(self, obs, now=None):
        if not obs:return False
        now=now or time.time(); ttl=obs.get("ttl_seconds")
        return ttl is None or (now-float(obs.get("observed_at",0))) <= float(ttl)

    @_world_locked
    def observations(self, domain, key=None, entity_id=None, include_stale=False):
        if domain not in DOMAINS: raise ValueError(f"unknown world domain: {domain}")
        entity=str(entity_id) if entity_id is not None else "__domain__"
        raw=self.state.get("observations",{}).get(domain,{}).get(entity,{})
        now=time.time(); out=[]
        for k,history in raw.items():
            if key is not None and k!=str(key): continue
            items=history if isinstance(history,list) else [history]
            for v in items:
                item=copy.deepcopy(v); item["fresh"]=self._observation_fresh(v,now); out.append(item)
        return sorted(out,key=lambda x:(x.get("confidence",0),x.get("observed_at",0)),reverse=True) if include_stale else sorted([x for x in out if x["fresh"]],key=lambda x:(x.get("confidence",0),x.get("observed_at",0)),reverse=True)

    @_world_locked
    def truth(self, domain, key, entity_id=None):
        """Return the best fresh observation plus uncertainty/conflict information."""
        obs=self.observations(domain,key,entity_id,include_stale=False)
        if not obs:return {"known":False,"value":None,"confidence":0.0,"conflict":False,"source":None}
        top=obs[0]; conflict=any(o.get("value")!=top.get("value") for o in obs[1:])
        return {"known":True,"value":copy.deepcopy(top.get("value")),"confidence":float(top.get("confidence",0)),"conflict":conflict,"source":top.get("source"),"observed_at":top.get("observed_at"),"fresh":True}

    @_world_locked
    def conflicts(self, domain=None):
        domains=[domain] if domain else sorted(DOMAINS)
        found=[]
        for d in domains:
            entities=self.state.get("observations",{}).get(d,{})
            for entity,keys in entities.items():
                for key in keys:
                    obs=self.observations(d,key,None if entity=="__domain__" else entity)
                    vals=[]
                    for o in obs:
                        if o.get("value") not in vals: vals.append(o.get("value"))
                    if len(vals)>1: found.append({"domain":d,"entity_id":None if entity=="__domain__" else entity,"key":key,"observations":obs})
        return found

    @_world_locked
    def update(self, domain, data, source="local", ttl_seconds=None, confidence=1.0):
        if domain not in DOMAINS: raise ValueError(f"unknown world domain: {domain}")
        now=time.time()
        wrapped=copy.deepcopy(data) if isinstance(data,dict) else {"value":copy.deepcopy(data)}
        wrapped["_meta"]={"observed_at":now,"source":str(source)[:160],"ttl_seconds":ttl_seconds,"confidence":self._confidence(confidence)}
        self.state[domain]=wrapped; self.state["updated"]=now
        if isinstance(data,dict):
            for key,value in data.items(): self.observe(domain,key,value,source,confidence,ttl_seconds)
        else: self.observe(domain,"value",data,source,confidence,ttl_seconds)
        self._event("world.updated",domain=domain,source=source); self._save(); return copy.deepcopy(self.state[domain])

    @_world_locked
    def merge(self, domain, patch, source="local", ttl_seconds=None, confidence=1.0):
        if domain not in DOMAINS: raise ValueError(f"unknown world domain: {domain}")
        current=self.state.get(domain,{})
        base={k:v for k,v in current.items() if k!="_meta"}
        if isinstance(patch,dict): base.update(copy.deepcopy(patch))
        return self.update(domain,base,source,ttl_seconds,confidence)

    @_world_locked
    def set_entity(self, domain, entity_id, data, source="local", ttl_seconds=None, confidence=1.0):
        if domain not in DOMAINS: raise ValueError(f"unknown world domain: {domain}")
        bucket=self.state.setdefault(domain,{})
        entities=bucket.setdefault("entities",{})
        now=time.time(); entities[str(entity_id)]={"data":copy.deepcopy(data),"observed_at":now,"source":str(source)[:160],"ttl_seconds":ttl_seconds,"confidence":self._confidence(confidence)}
        bucket["_meta"]={"observed_at":now,"source":str(source)[:160],"ttl_seconds":ttl_seconds,"confidence":self._confidence(confidence)}
        if isinstance(data,dict):
            for key,value in data.items(): self.observe(domain,key,value,source,confidence,ttl_seconds,entity_id)
        else: self.observe(domain,"value",data,source,confidence,ttl_seconds,entity_id)
        self.state["updated"]=now; self._event("entity.updated",domain=domain,entity_id=str(entity_id),source=source); self._save()
        return copy.deepcopy(entities[str(entity_id)])

    @_world_locked
    def get_entity(self, domain, entity_id): return copy.deepcopy(self.state.get(domain,{}).get("entities",{}).get(str(entity_id)))

    @staticmethod
    def _fresh(meta, now=None):
        if not meta:return False
        now=now or time.time(); ttl=meta.get("ttl_seconds")
        return ttl is None or (now-float(meta.get("observed_at",0))) <= float(ttl)

    @_world_locked
    def freshness(self, domain, entity_id=None):
        now=time.time()
        if entity_id is not None:
            item=self.get_entity(domain,entity_id)
            if not item:return {"known":False,"fresh":False,"age_seconds":None}
            age=max(0,now-float(item.get("observed_at",0)))
            return {"known":True,"fresh":self._fresh(item,now),"age_seconds":round(age,2),"source":item.get("source",""),"confidence":item.get("confidence",0.5)}
        meta=self.state.get(domain,{}).get("_meta",{})
        age=max(0,now-float(meta.get("observed_at",0))) if meta else None
        return {"known":bool(meta),"fresh":self._fresh(meta,now),"age_seconds":round(age,2) if age is not None else None,"source":meta.get("source",""),"confidence":meta.get("confidence",0.5)}

    @_world_locked
    def stale_domains(self): return [d for d in sorted(DOMAINS) if self.state.get(d,{}).get("_meta") and not self._fresh(self.state[d].get("_meta"))]
    @_world_locked
    def record_event(self,event,**data): self._event(event,**data); self._save(); return self.state["events"][-1]
    @_world_locked
    def _event(self,event,**data):
        self.state.setdefault("events",[]).append({"id":uuid.uuid4().hex[:12],"time":time.time(),"event":event,"data":data}); self.state["events"]=self.state["events"][-200:]
    @_world_locked
    def snapshot(self): return copy.deepcopy(self.state)
    @_world_locked
    def context(self,max_chars=16000):
        payload=self.snapshot(); payload["freshness"]={d:self.freshness(d) for d in sorted(DOMAINS)}; payload["stale_domains"]=self.stale_domains(); payload["conflicts"]=self.conflicts()
        return json.dumps(payload,indent=2,ensure_ascii=False,default=str)[:max_chars]

    @_world_locked
    def planning_summary(self, request, *, max_chars=1200):
        """Return request-relevant freshness metadata without observation values."""
        query=str(request or "").casefold()
        selected=[]
        for domain,terms in PLANNING_DOMAIN_TERMS.items():
            if any(re.search(r"(?<!\w)"+re.escape(term)+r"(?!\w)",query) for term in terms):
                fresh=self.freshness(domain)
                selected.append({
                    "domain":domain,
                    "known":bool(fresh.get("known")),
                    "fresh":bool(fresh.get("fresh")),
                    "age_seconds":fresh.get("age_seconds"),
                    "confidence":round(float(fresh.get("confidence",0.0)),3),
                    "provenance":"local_observation_ledger",
                })
        if not selected:
            return ""
        summary={
            "kind":"world_model_planning_summary",
            "trust":"observation_only",
            "policy":"metadata_only; observation values and entity identifiers omitted",
            "domains":selected,
        }
        limit=max(256,min(2000,int(max_chars)))
        return json.dumps(summary,sort_keys=True,separators=(",",":"),ensure_ascii=False)[:limit]
