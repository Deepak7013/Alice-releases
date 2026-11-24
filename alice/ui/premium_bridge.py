"""Local pywebview bridge for ALICE's supplied premium interface."""
from __future__ import annotations
import re
import ctypes
import os
import shutil
import time
import csv
import threading
import base64
import json
from pathlib import Path
from datetime import datetime, timezone

class PremiumUIBridge:
    """Expose narrow chat/status and user-directed memory operations."""

    def __init__(self, app=None):
        self.app = app
        self._brain_test_lock = threading.Lock()
        self._brain_test_running = False

    def bind(self, app):
        self.app = app

    def _current_app(self):
        return self.app

    def send_message(self, text):
        message = str(text or "").strip()
        if not message:
            return {"ok": False, "error": "Message is empty."}
        if len(message) > 20_000:
            return {"ok": False, "error": "Message is too long."}
        app=self._current_app()
        if app is None:return {"ok": False, "error": "ALICE is still starting; try again in a moment."}
        app._queue_ui("premium_submit", message)
        return {"ok": True}

    def poll_events(self, after=0):
        try:
            cursor = max(0, int(after))
        except (TypeError, ValueError):
            cursor = 0
        app=self._current_app()
        if app is None:return []
        with app._premium_event_lock:
            return [dict(event) for event in app._premium_events if event["id"] > cursor]

    def get_status(self):
        app=self._current_app()
        if app is None:return {"version":"starting", "provider":"ALICE runtime starting"}
        voice=getattr(app,"voice",None)
        return {"version": app._app_version(), "provider": app.provider_status(),
                "speak_mode": bool(voice and voice.is_enabled() and not getattr(app,"text_mode",True))}

    def list_browser_tabs(self):
        """Read the current persistent ALICE browser tabs without navigating."""
        app=self._current_app(); registry=getattr(app,"tools",None) if app is not None else None
        tool=registry.get("browser_tabs") if registry is not None else None
        if tool is None:return {"ok":False,"error":"ALICE’s controlled browser is not available."}
        try:
            result=tool.fn()
            rows=result.get("tabs",[]) if isinstance(result,dict) else result
            if not isinstance(rows,(list,tuple)):rows=[]
            items=[]
            for row in rows[:40]:
                if not isinstance(row,dict):continue
                url=str(row.get("url", ""))[:1000]
                if not url.lower().startswith(("https://","http://")):url=""
                items.append({"title":str(row.get("title", "Untitled tab"))[:160],"url":url,
                              "active":bool(row.get("active",row.get("is_active",False)))})
            return {"ok":True,"tabs":items}
        except Exception:return {"ok":False,"error":"Could not read ALICE browser tabs."}

    def list_applications(self, query="", limit=40):
        """Read installed and running app metadata through ALICE's discovery tools."""
        app=self._current_app(); registry=getattr(app,"tools",None) if app is not None else None
        if registry is None:return {"ok":False,"error":"Application discovery is not available."}
        output={"ok":True,"installed":[],"running":[]}
        try:
            tool=registry.get("discover_apps")
            if tool is not None:
                raw=tool.fn(query=str(query or "")[:100],limit=max(1,min(int(limit),80)))
                rows=raw.get("apps",[]) if isinstance(raw,dict) else raw
                output["installed"]=[{"name":str(row.get("name",""))[:180],"path":str(row.get("path",""))[:240],"publisher":""} for row in rows[:80] if isinstance(row,dict)]
            tool=registry.get("running_apps")
            if tool is not None:
                raw=tool.fn(query=str(query or "")[:100]);rows=raw.get("processes",raw.get("apps",[])) if isinstance(raw,dict) else raw
                output["running"]=[]
                for row in rows[:80]:
                    if isinstance(row,dict):
                        output["running"].append({"name":str(row.get("name",row.get("image","")))[:180],"pid":str(row.get("pid",""))[:20],"title":""})
                    elif isinstance(row,str):
                        fields=next(csv.reader([row]),[])
                        if fields:output["running"].append({"name":fields[0][:180],"pid":fields[1][:20] if len(fields)>1 else "","title":""})
            return output
        except Exception:return {"ok":False,"error":"Could not read installed or running applications."}

    def list_workspace_files(self, query="", limit=80):
        """Read file names/size metadata from ALICE's configured workspace only."""
        app=self._current_app();registry=getattr(app,"tools",None) if app is not None else None
        tool=registry.get("list_files") if registry is not None else None
        if tool is None:return {"ok":False,"error":"ALICE workspace file listing is not available."}
        try:
            raw=tool.fn(path=".")
            rows=raw.get("files",[]) if isinstance(raw,dict) else raw
            items=[]
            from ..workspace.files import safe_path
            root=safe_path(".")
            q=str(query or "").casefold()[:200]
            for row in rows if isinstance(rows,(list,tuple)) else []:
                name=str(row.get("name",row.get("path",""))) if isinstance(row,dict) else str(row)
                if q and q not in name.casefold():continue
                try:
                    path=safe_path(name)
                    if root not in path.parents or not path.is_file():continue
                    size=path.stat().st_size
                except Exception:size=0
                items.append({"name":name[:260],"kind":"file","size_bytes":size})
                if len(items)>=max(1,min(int(limit),100)):break
            return {"ok":True,"files":items}
        except Exception:return {"ok":False,"error":"Could not list ALICE workspace files."}

    def preview_workspace_file(self, name, max_bytes=65536):
        """Read a small text preview from the ALICE workspace, rejecting traversal and binaries."""
        from ..workspace.files import safe_path
        try:
            relative=Path(str(name or ""))
            if relative.is_absolute():return {"ok":False,"error":"Choose a relative workspace file."}
            target=safe_path(str(relative))
            root=safe_path(".")
            if root not in target.parents or not target.is_file():return {"ok":False,"error":"That workspace file is unavailable."}
            limit=max(1024,min(int(max_bytes),65536))
            with target.open("rb") as stream:raw=stream.read(limit+1)
            if b"\0" in raw:return {"ok":False,"error":"This file is binary and has no text preview."}
            truncated=len(raw)>limit
            text=raw[:limit].decode("utf-8",errors="replace")
            return {"ok":True,"name":str(relative).replace("\\","/"),"text":text,"truncated":truncated,"bytes_read":min(len(raw),limit)}
        except Exception:return {"ok":False,"error":"Could not preview that workspace file."}

    def get_system_health(self):
        """Read bounded host telemetry; unavailable sensors are explicitly null."""
        result={"ok":True,"cpu_percent":None,"ram_percent":None,
                "storage_used_gib":None,"storage_total_gib":None,"battery_percent":None,
                "gpu_percent":None,"temperature_c":None,"network":"Not measured",
                "sampled_at":datetime.now(timezone.utc).isoformat()}
        try:
            if os.name == "nt":
                class FILETIME(ctypes.Structure):
                    _fields_=[("low",ctypes.c_uint32),("high",ctypes.c_uint32)]
                    def value(self):return (int(self.high)<<32)|int(self.low)
                idle,kernel,user=FILETIME(),FILETIME(),FILETIME()
                if ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle),ctypes.byref(kernel),ctypes.byref(user)):
                    now=(idle.value,kernel.value,user.value); previous=getattr(self,"_health_cpu_snapshot",None)
                    self._health_cpu_snapshot=now
                    if previous is not None:
                        di,dk,du=(now[i]-previous[i] for i in range(3)); total=dk+du
                        if total>0:result["cpu_percent"]=round(max(0,min(100,(total-di)*100/total)),1)
                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_=[("length",ctypes.c_uint32),("memory_load",ctypes.c_uint32),
                              ("total_phys",ctypes.c_uint64),("avail_phys",ctypes.c_uint64),
                              ("total_page",ctypes.c_uint64),("avail_page",ctypes.c_uint64),
                              ("total_virtual",ctypes.c_uint64),("avail_virtual",ctypes.c_uint64),
                              ("avail_extended",ctypes.c_uint64)]
                mem=MEMORYSTATUSEX();mem.length=ctypes.sizeof(mem)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)) and mem.total_phys:
                    result["ram_percent"]=round((mem.total_phys-mem.avail_phys)*100/mem.total_phys,1)
            else:
                try:
                    import psutil
                    result["cpu_percent"]=float(psutil.cpu_percent(interval=None))
                    result["ram_percent"]=float(psutil.virtual_memory().percent)
                except Exception:pass
        except Exception:pass
        # Some Windows/WebView launch contexts expose GetSystemTimes and
        # GlobalMemoryStatusEx inconsistently. Use psutil only for readings
        # the native APIs did not provide, so the UI shows real host metrics
        # instead of leaving CPU/RAM blank.
        try:
            import psutil
            if result["cpu_percent"] is None:
                result["cpu_percent"]=float(psutil.cpu_percent(interval=None))
            if result["ram_percent"] is None:
                result["ram_percent"]=float(psutil.virtual_memory().percent)
        except Exception:pass
        try:
            anchor=Path.home().anchor or str(Path.home())
            usage=shutil.disk_usage(anchor); gib=1024**3
            result["storage_used_gib"]=round((usage.total-usage.free)/gib,1)
            result["storage_total_gib"]=round(usage.total/gib,1)
        except Exception:pass
        try:
            from ..computer.system_tools import WindowsHardware
            battery=WindowsHardware().battery_status()
            if battery.get("ok") and battery.get("battery_present") is not False:
                result["battery_percent"]=battery.get("percent")
        except Exception:pass
        return result

    def get_brain_status(self):
        """Return provider readiness and optional local-model status without secrets."""
        app=self._current_app()
        router=getattr(app,"router",None) if app is not None else None
        if router is None or not callable(getattr(router,"local_status",None)):
            return {"ok":False,"error":"Local brain status is not available yet."}
        try:
            state=router.local_status()
            if not isinstance(state,dict):
                return {"ok":False,"error":"Local brain returned an invalid status."}
            models=state.get("models",[])
            if not isinstance(models,(list,tuple)):
                models=[]
            fast=str(getattr(router,"local_fast_model", "") or "")
            primary_resolver=getattr(router,"primary_provider",None)
            if callable(primary_resolver):
                primary=str(primary_resolver() or "local")
            else:
                policy_mode=str(getattr(getattr(router,"runtime_policy",None),"mode","gemini_primary"))
                primary=("gemini" if policy_mode=="gemini_primary" else
                         policy_mode[:-8] if policy_mode.endswith("_primary") else "local")
            mode=str(getattr(getattr(router,"runtime_policy",None),"mode","gemini_primary"))
            gemini_primary=primary=="gemini"
            gemini_configured=bool(router.available().get("gemini")) if callable(getattr(router,"available",None)) else bool(os.getenv("GEMINI_API_KEY"," ").strip())
            if primary=="gemini": primary_model=str(getattr(router,"gemini_model","gemini-3.8-flash"))
            elif primary=="local": primary_model=str(state.get("model", ""))
            else:
                _key,_model,_base=router._HOSTED_CONFIG.get(primary,("","",""))
                primary_model=str(os.getenv(_model,""))
            configured=bool(router.available().get(primary)) if primary!="local" else bool(state.get("model_available"))
            return {"ok":True,
                    "primary_provider":primary,
                    "primary_model":primary_model[:120],
                    "provider_configured":configured,
                    "gemini_configured":gemini_configured,
                    "gemini_connection":"not_tested" if gemini_primary and gemini_configured else ("setup_required" if gemini_primary else "not_primary"),
                    "ollama_installed":bool(state.get("installed")),
                    "reachable":bool(state.get("reachable")),
                    "model":str(state.get("model", ""))[:120],
                    "model_available":bool(state.get("model_available")),
                    "quick_model":fast[:120],
                    "quick_model_available":bool(fast and any(str(x)==fast for x in models)),
                    "installed_models":[str(x)[:120] for x in models[:30]],
                    "api_key_required":bool(primary not in {"local"} and not configured)}
        except Exception:
            return {"ok":False,"error":"Could not read local brain readiness."}

    def list_automations(self):
        """Expose schedule metadata only; scheduled prompts remain in the native manager."""
        app=self._current_app()
        scheduler=getattr(getattr(app,"runtime",None),"scheduler",None) if app is not None else None
        if scheduler is None or not callable(getattr(scheduler,"list",None)):
            return {"ok":False,"error":"ALICE’s local scheduler is not available yet."}
        try:
            rows=scheduler.list()
            items=[]
            for row in rows:
                if not isinstance(row,dict):
                    continue
                items.append({"id":str(row.get("id", ""))[:24],
                              "name":str(row.get("name", "Untitled schedule"))[:120],
                              "interval_seconds":max(0,int(row.get("interval_seconds",0) or 0)),
                              "enabled":bool(row.get("enabled")),
                              "next_run":float(row.get("next_run",0) or 0),
                              "last_run":float(row.get("last_run",0) or 0)})
            return {"ok":True,"automations":items[:100]}
        except Exception:
            return {"ok":False,"error":"Could not read ALICE’s local schedules."}

    def get_learning_status(self):
        """Expose aggregate learning counters without lesson text or user prompts."""
        app=self._current_app()
        engine=getattr(app,"learning",None) if app is not None else None
        if engine is None or not callable(getattr(engine,"stats",None)):
            return {"ok":False,"error":"ALICE learning status is not available yet."}
        try:
            raw=engine.stats()
            if not isinstance(raw,dict):
                return {"ok":False,"error":"ALICE learning returned an invalid status."}
            keys=("experience_records","successful","failed","lessons","promoted",
                  "eval_cases","regression_seeds","verified_recoveries","regressions")
            return {"ok":True,"counters":{key:max(0,int(raw.get(key,0) or 0)) for key in keys}}
        except Exception:
            return {"ok":False,"error":"Could not read ALICE learning status."}

    def search_knowledge(self, query, limit=10):
        """Search locally stored knowledge and return bounded source provenance."""
        text=str(query or "").strip()[:300]
        if not text:
            return {"ok":False,"error":"Enter a topic to search local knowledge."}
        app=self._current_app()
        acquirer=getattr(app,"knowledge_acquirer",None) if app is not None else None
        search=getattr(acquirer,"search",None)
        if not callable(search):
            return {"ok":False,"error":"Local knowledge retrieval is not available yet."}
        try:
            rows=search(text,limit=max(1,min(int(limit),20)))
            items=[]
            for row in rows if isinstance(rows,list) else []:
                if not isinstance(row,dict):
                    continue
                source=row.get("source") if isinstance(row.get("source"),dict) else {}
                kind=str(source.get("kind", "unknown"))[:40]
                locator=str(source.get("locator", ""))
                if not locator.lower().startswith(("https://", "http://")):
                    locator=""
                else:
                    # Do not surface query strings or fragments that can carry tokens.
                    from urllib.parse import urlsplit, urlunsplit
                    parts=urlsplit(locator)
                    host=parts.hostname or ""
                    try:
                        if parts.port:host=f"{host}:{parts.port}"
                    except ValueError:
                        host=""
                    locator=urlunsplit((parts.scheme,host,parts.path,"",""))[:500]
                items.append({"id":str(row.get("id", ""))[:24],
                              "topic":str(row.get("topic", ""))[:200],
                              "text":str(row.get("text", ""))[:1600],
                              "source_kind":kind,
                              "source_title":str(source.get("title", ""))[:200],
                              "source_url":locator,
                              "confidence":max(0.0,min(1.0,float(row.get("confidence",0) or 0))),
                              "trusted":bool(row.get("trusted")),
                              "updated_at":float(row.get("updated_at",0) or 0)})
            return {"ok":True,"query":text,"items":items[:20]}
        except Exception:
            return {"ok":False,"error":"Local knowledge search failed."}

    def get_reasoning_activity(self, limit=20):
        """Return safe task lifecycle metadata; audit payloads and prompts stay private."""
        app=self._current_app()
        audit=getattr(getattr(app,"runtime",None),"audit",None) if app is not None else None
        recent=getattr(audit,"recent",None)
        if not callable(recent):
            return {"ok":False,"error":"ALICE activity history is not available yet."}
        try:
            rows=recent(max(1,min(int(limit)*4,100)))
            items=[]
            allowed={"task_submitted":"Task received","task_started":"Task started",
                     "task_returned":"Task finished","task_cancelled":"Task cancelled",
                     "event_handler_error":"Runtime event error"}
            for row in rows if isinstance(rows,list) else []:
                if not isinstance(row,dict):
                    continue
                event=str(row.get("event", ""))
                if event not in allowed:
                    continue
                data=row.get("data") if isinstance(row.get("data"),dict) else {}
                state=str(data.get("state", ""))[:40]
                items.append({"title":allowed[event],
                              "state":state or ("recorded" if event!="task_returned" else "status unavailable"),
                              "verified":data.get("verified") is True,
                              "time":str(row.get("time", ""))[:40]})
            return {"ok":True,"items":items[-max(1,min(int(limit),50)):][::-1]}
        except Exception:
            return {"ok":False,"error":"Could not read ALICE activity history."}

    @staticmethod
    def _memory_id(value):
        memory_id = str(value or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{8,32}", memory_id):
            return None
        return memory_id

    @staticmethod
    def _memory_payload(record):
        get = record.get if isinstance(record, dict) else lambda key, default=None: getattr(record, key, default)
        updated_at = get("updated_at", 0)
        return {
            "id": str(get("id", ""))[:12],
            "kind": str(get("kind", ""))[:80],
            "key": str(get("key", ""))[:300],
            "value": str(get("value", ""))[:3000],
            "source": str(get("source", ""))[:120],
            "confidence": round(float(get("confidence", 0.0)), 3),
            "updated_at": datetime.fromtimestamp(
                float(updated_at), timezone.utc
            ).isoformat() if updated_at else "",
        }

    @staticmethod
    def _resolve_memory(manager, prefix):
        matches = [record for record in manager.list(limit=100)
                   if str(record.id).startswith(prefix)]
        if len(matches) != 1:
            return None, len(matches)
        return matches[0], 1

    def list_memories(self):
        """Return active structured memories only; never expose database paths."""
        app = self._current_app()
        memory = getattr(app, "memory", None) if app is not None else None
        manager = getattr(memory, "manager", None)
        if manager is None:
            return {"ok": False, "error": "ALICE memory is not available yet."}
        try:
            records = manager.list(limit=100)
            return {"ok": True, "memories": [self._memory_payload(r) for r in records]}
        except Exception:
            return {"ok": False, "error": "Could not read ALICE's structured memory."}

    def correct_memory(self, memory_id, new_value):
        """Correct one memory selected by its displayed ID prefix."""
        selected = self._memory_id(memory_id)
        value = str(new_value or "").strip()
        if selected is None:
            return {"ok": False, "error": "Select a memory using its 8-character ID."}
        if not value:
            return {"ok": False, "error": "The corrected memory cannot be empty."}
        if len(value) > 3000:
            return {"ok": False, "error": "The corrected memory is too long (maximum 3,000 characters)."}
        app = self._current_app()
        manager = getattr(getattr(app, "memory", None), "manager", None) if app else None
        if manager is None:
            return {"ok": False, "error": "ALICE memory is not available yet."}
        try:
            record, count = self._resolve_memory(manager, selected)
            if record is None:
                reason = "No active memory has that ID." if count == 0 else "That ID matches multiple memories. Refresh and select a longer ID."
                return {"ok": False, "error": reason}
            result = manager.correct(record.id, value, source="user_memory_editor")
            if not result.get("ok"):
                return {"ok": False, "error": str(result.get("reason", "Memory could not be corrected."))}
            return {"ok": True, "memory": self._memory_payload(result["new"])}
        except Exception:
            return {"ok": False, "error": "Could not correct that memory."}

    def forget_memory(self, memory_id, confirmed=False):
        """Forget exactly one selected memory, only after a UI confirmation."""
        if confirmed is not True:
            return {"ok": False, "error": "Confirm forgetting this memory first."}
        selected = self._memory_id(memory_id)
        if selected is None:
            return {"ok": False, "error": "Select a memory using its 8-character ID."}
        app = self._current_app()
        manager = getattr(getattr(app, "memory", None), "manager", None) if app else None
        if manager is None:
            return {"ok": False, "error": "ALICE memory is not available yet."}
        try:
            record, count = self._resolve_memory(manager, selected)
            if record is None:
                reason = "No active memory has that ID; nothing was forgotten." if count == 0 else "That ID matches multiple memories; nothing was forgotten."
                return {"ok": False, "error": reason}
            result = manager.forget(record.id, limit=1)
            if not result.get("ok") or result.get("forgotten") != 1:
                return {"ok": False, "error": "That memory was not found or was ambiguous; nothing was forgotten."}
            return {"ok": True, "forgotten": 1, "id": selected}
        except Exception:
            return {"ok": False, "error": "Could not forget that memory."}

    def list_tasks(self, limit=20):
        """Read recent local task records without exposing their storage paths."""
        app = self._current_app()
        manager = getattr(app, "tasks", None) if app is not None else None
        if manager is None:
            return {"ok": False, "error": "ALICE task history is not available yet."}
        try:
            count = max(1, min(int(limit), 50))
            rows = manager.list_tasks(limit=count)
            tasks = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                tasks.append({
                    "id": str(row.get("id", ""))[:24],
                    "status": str(row.get("status", "unknown"))[:40],
                    "request": str(row.get("request", ""))[:600],
                    "result": str(row.get("result", ""))[:1200],
                    "started": float(row.get("started", 0) or 0),
                    "finished": float(row.get("finished", 0) or 0),
                })
            return {"ok": True, "tasks": tasks}
        except Exception:
            return {"ok": False, "error": "Could not read ALICE's local task history."}

    def open_native_panel(self, panel):
        """Open an existing ALICE dialog/menu from the Premium workspace."""
        allowed={"tools","updates","voice","goals","approvals","devour","history","brain"}
        selected=str(panel or "").strip().lower()
        app=self._current_app()
        if app is None:return {"ok":False,"error":"ALICE is still starting."}
        if selected not in allowed:return {"ok":False,"error":"Unknown workspace panel."}
        # Brain Setup is rendered by the visible WebView. Opening a Tk modal
        # whose owner is deliberately withdrawn hid the dialog behind ALICE.
        if selected == "brain":
            return {"ok":True,"panel":"brain","mode":"embedded"}
        app._queue_ui("premium_native_panel",selected)
        return {"ok":True}

    def gemini_setup_status(self):
        app=self._current_app()
        if app is None:return {"ok":False,"error":"ALICE is still starting."}
        router=getattr(app,"router",None)
        if router is None:return {"ok":False,"error":"ALICE's provider router is not ready."}
        try:
            return {"ok":True,"configured":bool(router.available().get("gemini")),
                    "model":str(getattr(router,"gemini_model","gemini-3.8-flash")),
                    "primary_provider":"gemini"}
        except Exception:
            return {"ok":False,"error":"Could not read Gemini setup status."}

    def save_gemini_settings(self, api_key="", model="gemini-3.8-flash"):
        """Save Gemini credentials locally; never return or log the key."""
        app=self._current_app()
        if app is None:return {"ok":False,"error":"ALICE is still starting."}
        try:
            from ..providers.configuration import save_gemini_config, save_gemini_model
            token=str(api_key or "").strip()
            selected=str(model or "").strip()
            if token:
                save_gemini_config(app.root_path/".env",token,selected)
            else:
                save_gemini_model(app.root_path/".env",selected)
            app.router.reload_config()
            return {"ok":True,"configured":bool(app.router.available().get("gemini")),
                    "model":str(getattr(app.router,"gemini_model",selected)),
                    "message":"Gemini settings saved locally. Connection has not been tested."}
        except Exception as exc:
            # Validation messages are safe; never reflect input or exception repr.
            return {"ok":False,"error":str(exc)[:240]}

    def test_gemini_connection(self, model=""):
        """Run the explicit provider check off the WebView thread."""
        app=self._current_app()
        if app is None:return {"ok":False,"error":"ALICE is still starting."}
        router=getattr(app,"router",None)
        if router is None:return {"ok":False,"error":"ALICE's provider router is not ready."}
        if not router.available().get("gemini"):
            return {"ok":False,"error":"Save a Gemini API key before testing."}
        with self._brain_test_lock:
            if self._brain_test_running:
                return {"ok":False,"error":"A Gemini connection test is already running."}
            self._brain_test_running=True
        selected=str(model or getattr(router,"gemini_model","gemini-3.8-flash")).strip()[:120]
        def run():
            try:
                result=router.test_gemini_connection(model=selected)
                payload={"ok":True,"model":str(result.get("model",selected)),
                         "elapsed_seconds":result.get("elapsed_seconds")}
            except Exception as exc:
                payload={"ok":False,"error":str(exc)[:300]}
            finally:
                with self._brain_test_lock:self._brain_test_running=False
            try:app._publish_premium_event("brain_connection_test",payload)
            except Exception:pass
        threading.Thread(target=run,name="alice-gemini-webview-test",daemon=True).start()
        return {"ok":True,"started":True}

    def save_hosted_provider_settings(self, provider="", api_key="", model=""):
        """Save an explicitly selected BYOK reasoning provider locally."""
        app=self._current_app()
        if app is None:return {"ok":False,"error":"ALICE is still starting."}
        try:
            from ..providers.configuration import save_hosted_provider_config
            selected=str(provider or "").strip().lower()
            save_hosted_provider_config(app.root_path/".env",selected,api_key,model)
            app.router.reload_config()
            return {"ok":True,"provider":selected,"model":str(model or "")[:160],
                    "message":f"{selected.title()} settings saved to this ALICE installation. Connection not tested."}
        except Exception as exc:
            return {"ok":False,"error":str(exc)[:240]}

    def test_hosted_provider_connection(self, provider="", api_key="", model=""):
        app=self._current_app()
        if app is None:return {"ok":False,"error":"ALICE is still starting."}
        router=getattr(app,"router",None)
        if router is None:return {"ok":False,"error":"ALICE's provider router is not ready."}
        with self._brain_test_lock:
            if self._brain_test_running:return {"ok":False,"error":"A provider connection test is already running."}
            self._brain_test_running=True
        selected=str(provider or "").strip().lower()
        def run():
            try:
                result=router.test_hosted_connection(selected,api_key=api_key,model=model)
                payload={"ok":True,"provider":selected,"model":str(result.get("model",model))[:160],
                         "elapsed_seconds":result.get("elapsed_seconds")}
            except Exception as exc:
                payload={"ok":False,"provider":selected,"error":str(exc)[:300]}
            finally:
                with self._brain_test_lock:self._brain_test_running=False
            try:app._publish_premium_event("brain_connection_test",payload)
            except Exception:pass
        threading.Thread(target=run,name="alice-provider-webview-test",daemon=True).start()
        return {"ok":True,"started":True}

    def set_speak_mode(self, enabled):
        app=self._current_app()
        if app is None:return {"ok":False,"error":"ALICE is still starting."}
        app._queue_ui("premium_speak_mode",bool(enabled))
        return {"ok":True,"enabled":bool(enabled)}

    def show_classic_ui(self):
        app=self._current_app()
        if app is None:return {"ok":False,"error":"ALICE is still starting."}
        app.root.after(0, app.root.deiconify)
        return {"ok": True}

    def minimize_to_mini(self):
        """Hide the main workspace and leave ALICE available from its tray icon."""
        app=self._current_app()
        if app is None:return {"ok":False,"error":"ALICE is still starting."}
        app._queue_ui("premium_minimize_to_mini",None)
        return {"ok":True,"message":"ALICE workspace hidden; use the tray icon to open Mini ALICE."}

    @staticmethod
    def _ui_preferences_path(app):
        base=Path(os.getenv("APPDATA") or (Path.home()/"AppData"/"Roaming"))
        return base/"ALICE"/"ui"/"preferences.json"

    def get_ui_preferences(self):
        """Return local visual preferences without exposing other user files."""
        app=self._current_app()
        if app is None:return {"ok":False,"error":"ALICE is still starting."}
        try:
            prefs_path=self._ui_preferences_path(app)
            prefs_path.parent.mkdir(parents=True,exist_ok=True)
            prefs=json.loads(prefs_path.read_text(encoding="utf-8")) if prefs_path.is_file() else {}
            background=Path(str(prefs.get("background_path", ""))).resolve() if prefs.get("background_path") else None
            background_color=str(prefs.get("background_color", "")).strip().lower()
            if not re.fullmatch(r"#[0-9a-f]{6}", background_color):
                background_color=""
            if background and background.is_file() and background.suffix.lower() in {".png",".jpg",".jpeg",".webp",".bmp"} and prefs.get("background_mode", "image") == "image":
                return {"ok":True,"background_uri":background.as_uri(),"background_color":background_color}
            if prefs.get("background_mode") == "color" and background_color:
                return {"ok":True,"background_uri":"","background_color":background_color}
            bundled=Path(__file__).resolve().parent/"assets"/"alice-default-wallpaper.png"
            return {"ok":True,"background_uri":bundled.as_uri() if bundled.is_file() else "","background_color":background_color}
        except Exception:
            bundled=Path(__file__).resolve().parent/"assets"/"alice-default-wallpaper.png"
            return {"ok":True,"background_uri":bundled.as_uri() if bundled.is_file() else ""}

    def save_ui_background(self, data_url, filename="background"):
        """Validate and persist a user-selected static wallpaper locally."""
        app=self._current_app()
        if app is None:return {"ok":False,"error":"ALICE is still starting."}
        match=re.fullmatch(r"data:image/(png|jpeg|webp|bmp);base64,([A-Za-z0-9+/=]+)",str(data_url or ""),re.I)
        if not match:return {"ok":False,"error":"Choose a PNG, JPEG, WebP, or BMP image."}
        ext={"jpeg":".jpg","png":".png","webp":".webp","bmp":".bmp"}[match.group(1).lower()]
        try:
            raw=base64.b64decode(match.group(2),validate=True)
            if not raw or len(raw)>12*1024*1024:return {"ok":False,"error":"Background images must be smaller than 12 MB."}
            from PIL import Image
            from io import BytesIO
            with Image.open(BytesIO(raw)) as image:
                if image.format not in {"PNG","JPEG","WEBP","BMP"} or image.width<64 or image.height<64 or image.width*image.height>50_000_000:
                    return {"ok":False,"error":"That image format or resolution is not supported."}
                image.verify()
            folder=self._ui_preferences_path(app).parent
            folder.mkdir(parents=True,exist_ok=True)
            target=folder/("home-background"+ext)
            temp=target.with_suffix(target.suffix+".tmp")
            temp.write_bytes(raw); temp.replace(target)
            prefs_path=folder/"preferences.json"
            try:prefs=json.loads(prefs_path.read_text(encoding="utf-8")) if prefs_path.is_file() else {}
            except Exception:prefs={}
            prefs["background_path"]=str(target)
            prefs["background_mode"]="image"
            tmp=prefs_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(prefs,indent=2),encoding="utf-8");tmp.replace(prefs_path)
            return {"ok":True,"background_uri":target.resolve().as_uri(),"filename":Path(str(filename)).name[:180]}
        except Exception:
            return {"ok":False,"error":"ALICE could not save that background image locally."}

    def save_ui_background_color(self, color):
        """Persist a user-selected solid workspace background color."""
        app=self._current_app()
        if app is None:return {"ok":False,"error":"ALICE is still starting."}
        value=str(color or "").strip().lower()
        if not re.fullmatch(r"#[0-9a-f]{6}", value):
            return {"ok":False,"error":"Choose a valid six-digit hex color."}
        try:
            prefs_path=self._ui_preferences_path(app)
            prefs_path.parent.mkdir(parents=True,exist_ok=True)
            try:prefs=json.loads(prefs_path.read_text(encoding="utf-8")) if prefs_path.is_file() else {}
            except Exception:prefs={}
            prefs["background_color"]=value
            prefs["background_mode"]="color"
            tmp=prefs_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(prefs,indent=2),encoding="utf-8");tmp.replace(prefs_path)
            return {"ok":True,"background_uri":"","background_color":value}
        except Exception:
            return {"ok":False,"error":"ALICE could not save that background color locally."}

    def clear_ui_background(self):
        """Restore the built-in ALICE background while retaining other preferences."""
        app=self._current_app()
        if app is None:return {"ok":False,"error":"ALICE is still starting."}
        try:
            prefs_path=self._ui_preferences_path(app)
            prefs_path.parent.mkdir(parents=True,exist_ok=True)
            prefs=json.loads(prefs_path.read_text(encoding="utf-8")) if prefs_path.is_file() else {}
            old=Path(str(prefs.pop("background_path",""))).resolve() if prefs.get("background_path") else None
            prefs.pop("background_color",None)
            prefs.pop("background_mode",None)
            tmp=prefs_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(prefs,indent=2),encoding="utf-8");tmp.replace(prefs_path)
            if old and old.parent==prefs_path.parent and old.name.startswith("home-background"):
                try:old.unlink(missing_ok=True)
                except Exception:pass
            bundled=Path(__file__).resolve().parent/"assets"/"alice-default-wallpaper.png"
            return {"ok":True,"background_uri":bundled.as_uri() if bundled.is_file() else ""}
        except Exception:
            return {"ok":False,"error":"Could not restore ALICE's built-in background."}

    def open_provider_setup(self):
        """Legacy bridge method retained for older bundled front ends."""
        app=self._current_app()
        if app is None:return {"ok":False,"error":"ALICE is still starting."}
        return {"ok":True}

    def save_provider_settings(self, api_key="", model="openrouter/auto", free_only=False):
        """Reject legacy hosted-provider forms without retaining their key."""
        return {"ok":False,"error":"ALICE Brain is local-only. AI provider API keys are not accepted; configure the local model in Brain Setup."}

