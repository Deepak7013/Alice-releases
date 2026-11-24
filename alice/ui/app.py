import os, threading, tkinter as tk, sys, subprocess, queue, json, time, re
from datetime import datetime, timezone
from pathlib import Path
from tkinter import messagebox, filedialog, simpledialog
from tkinter import scrolledtext, ttk
from ..providers.router import Router
from ..tools.registry import ToolRegistry
from ..workspace.files import list_files,read_file,write_file
from ..computer.windows import open_app,open_url
from ..browser.web import fetch
from ..browser.playwright_browser import BrowserAgent
from ..browser.postconditions import verify_browser_click_postcondition
from ..terminal.windows import WindowsTerminal
from ..vision.screen import screenshot
from ..computer.controller import ComputerController
from ..computer.discovery import AppDiscovery
from ..brain.intent_router import IntentRouter
from ..finance import register_trading_tools
from ..finance.service import is_trading_request
from ..vision.grounding import ScreenGrounder
from ..agent.agent import AliceAgent
from ..maintenance.self_manager import SelfManager
from ..voice.voice import Voice
from ..voice.input import MicrophoneManager
from ..voice.jarvis_listener import JarvisAdvancedListener
from ..memory.store import MemoryStore
from ..creation.service import CreationService
from ..creation.models import CreationRequest, ArtifactKind
from ..creation.image import OpenAIImageProvider
from ..conversation.persistent import PersistentConversation
from ..integrations.catalog import IntegrationCatalog
from ..email.tooling import register_email_tools
from ..email.gmail import GmailCredentialStore, GmailReadOnlyProvider
from ..android_intelligence.summary import read_mail_unread_count
from ..core.task_manager import TaskManager
from ..builder.engine import BuilderEngine
from ..research.web_research import WebResearch
from ..capabilities.manager import CapabilityManager
from ..capabilities.skills import SkillForge
from ..capabilities.dependencies import DependencyManager
from ..capabilities.acquisition import CapabilityAcquirer
from ..capabilities.recovery import CapabilityRecovery
from ..voice.reliability import VoiceReliability
from ..knowledge.acquirer import KnowledgeAcquirer
from ..knowledge.security import redact_secrets
from ..mobile.android import AndroidController
from ..agents.orchestrator import MultiAgentOrchestrator
from ..agents.worker import WorkerSpec
from ..world.model import WorldModel
from ..supervisor.supervisor import AutonomousSupervisor
from ..runtime.runtime import AliceRuntime
from ..desktop.control import GlobalHotkey
from ..deployment.updater import InPlaceUpdater, version_tuple
from ..deployment.update_service import UpdateService
from ..deployment.signed_updates import verify_signed_package, public_key_from_file, enroll_trusted_key
from ..cognitive.core import CognitiveCore
from ..reasoning.engine import ReasoningEngine
from ..proactive.manager import ProactiveManager
from ..goals import GoalEngine
from ..horizon import HorizonManager
from ..council import CouncilEngine
from ..learning.engine import LearningEngine
from ..gluttony import AssimilationEngine, DevourEngine
from ..gluttony.review import DevourReviewStore
from ..remote.lifecycle import DEFAULT_LOOPBACK_PORT, RemoteMobileServiceController, start_configured_service, write_config
from ..remote.http_service import verify_private_health_url
from ..remote.pairing_store import DPAPIPairingStore
from .response_transaction import ResponseTransaction
from .hud_chatbox import HUDChatbox

from alice.ui.response_delivery import canonicalize_response
class AliceUI:
    @staticmethod
    def _app_version():
        configured=os.getenv("ALICE_APP_VERSION","").strip()
        if configured:
            return configured
        try:
            return (Path(__file__).resolve().parents[2] / "VERSION.txt").read_text(encoding="utf-8").strip().replace("ALICE ", "")
        except Exception:
            return "v4.1.0"

    @classmethod
    def _generation_name(cls):
        names={1:"Genesis",2:"Awakening",3:"Gluttony",4:"Elysium",5:"Sovereign",6:"Ascendant",7:"Apex",8:"Eternity",9:"Omniscience",10:"Singularity"}
        try:
            v=cls._app_version().lstrip("v").split(".",1)[0]
            return "ALICE "+names.get(int(v),"Elysium")
        except Exception:
            return "ALICE Elysium"

    def __init__(self):
        self._nus_sidecar=os.getenv("ALICE_NUS_SIDECAR","0").lower() in {"1","true","yes","on"}
        self.root=tk.Tk()
        if self._nus_sidecar:getattr(self.root,"withdraw")()
        self.root.title(f"Alice — {self._generation_name()} {self._app_version()}"); self.root.geometry("1180x800"); self.root.minsize(860,620); self._ui_queue=queue.Queue(); self._pending_ui_item=None
        self._premium_event_lock=threading.Lock(); self._premium_events=[]; self._premium_event_seq=0; self._premium_window=None
        self.updates=UpdateService(self.root_path); self._update_recovery_blocked=False
        try:
            if not self.updates.startup_allowed():
                messagebox.showinfo("ALICE update in progress","The ALICE updater is applying a signed package. Wait for it to finish, then start ALICE again.",parent=self.root)
                self.root.destroy(); raise SystemExit(4)
        except SystemExit:
            raise
        except Exception as exc:
            self._update_recovery_blocked=True; self._update_recovery={"ok":False,"error":type(exc).__name__}
        self._window_state_path=self.root_path / "alice_workspace" / "runtime" / "window.json"
        self._bubble_state_path=self.root_path / "alice_workspace" / "runtime" / "bubble.json"
        self._hud_chatbox=None; self._hud_chat_enabled=self._read_hud_chat_state()
        self._window_save_after=None; self._bubble_drag=None; self._bubble_menu=None
        self.router=Router(); self.memory=MemoryStore(); self.conversation=PersistentConversation(); self.integrations=IntegrationCatalog(self.root_path); self.capabilities=CapabilityManager(); self.world=WorldModel()
        self.app_discovery=AppDiscovery(); self.web_research=WebResearch()
        self.intent_router=IntentRouter(self.app_discovery,self.web_research)
        self.knowledge_acquirer=KnowledgeAcquirer(self.router,self.web_research,root=self.root_path); self.gluttony=AssimilationEngine(self.root_path); self.devour=DevourEngine(self.root_path,self.gluttony,capability_manager=self.capabilities); self.devour.self_manager.router=self.router; self.devour_reviews=DevourReviewStore(self.root_path); self.tools=self.build_tools()
        self.capability_acquirer=CapabilityAcquirer(self.router,self.capabilities,researcher=self.web_research,root=self.root_path)
        self.capability_recovery=CapabilityRecovery(self.capability_acquirer)
        self.agent=AliceAgent(self.router,self.tools,memory=self.memory,capabilities=self.capabilities,capability_recovery=self.capability_recovery,knowledge_acquirer=self.knowledge_acquirer,world_model=self.world); self.multi_agent=MultiAgentOrchestrator(self.router,self.tools); self.supervisor=AutonomousSupervisor(self.agent,self.multi_agent,self.world); self.tasks=TaskManager(self.agent); self.voice=Voice(); self.voice.set_activity_callback(lambda state:self._publish_orb_state(state)); self.voice_reliability=VoiceReliability(self.voice); self.microphone=MicrophoneManager(self.root_path); self.jarvis_listener=JarvisAdvancedListener(self.microphone,on_status=lambda message:self._queue_ui("jarvis_status",message),on_transcript=lambda text,translated:self._queue_ui("jarvis_transcript",text,translated),on_partial=lambda text:self._queue_ui("jarvis_partial",text)); self.runtime=AliceRuntime(agent=self.agent,world=self.world); self.cognitive=CognitiveCore(self.memory,self.runtime,self.router,world_model=self.world); self.reasoning=ReasoningEngine(self.router,self.memory); self.proactive=ProactiveManager(self.runtime); self.goals=GoalEngine(self.root_path); self.horizon=HorizonManager(self.root_path); self.council=CouncilEngine(); self.learning=LearningEngine(self.root_path); self.runtime.events.subscribe("task.completed", self._learn_task_completed); self.runtime.events.subscribe("task.failed", self._learn_task_failed); self.runtime.events.subscribe("task.observed", self._learn_task_observed)
        self.text_mode=True; self.concise_mode=True; self._cancel_event=None; self._shutdown=False; self.last_response=""; self._stream_event=None; self._streaming=False
        # Keep the resident assistant warm when the user closes the window.
        # Ctrl+Alt+A can then restore the existing UI instead of paying the
        # full provider/runtime initialization cost on every open.
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
        self._mini_window=None; self._mini_transcript_widget=None; self._mini_input=None; self._mini_attachments=[]; self._tray_icon=None
        self._build_main_ui(); self._restore_window_state(); self._restore_conversation()
        if not self._nus_sidecar:
            self._build_floating_indicator(); self._start_tray_icon()
        else:
            # Nūs owns the visible interface and its Knot. Keep ALICE's Tk
            # dispatcher alive in the background without creating a second UI,
            # tray icon, or global hotkey.
            getattr(self.root,"withdraw")()
        self.root.after(25,self._drain_ui_queue); self._write_startup_health()
        try:self._update_recovery=self.updates.recover_interrupted()
        except Exception as exc:self._update_recovery={"ok":False,"error":type(exc).__name__}; self._update_recovery_blocked=True
        self._schedule_auto_update_check()
        if self._hud_chat_enabled and not self._nus_sidecar: self.root.after(300,self._open_hud_chatbox)
        self.hotkey=None
        if not self._nus_sidecar:
            self.hotkey=GlobalHotkey(lambda:self._queue_ui("mini_hotkey")); self.hotkey.start()
        self.runtime.start_scheduler()
        self.remote_mobile_service=None
        try:
            self.remote_mobile_service=start_configured_service(self.agent,self.root_path,version=self._app_version(),email_service=getattr(self,"email_service",None))
        except Exception as exc:
            # Do not put pairing material or request data in the audit log.
            self.runtime.audit.record("remote_mobile_start_failed",error=type(exc).__name__)
        if not self._nus_sidecar:
            self.say("Alice","I'm awake. Streaming chat is ON. Text mode is ON and Concise mode is ON. Press Ctrl+Alt+A to show or hide me.")
        # A terminal ROLLED_BACK journal can persist across launches. Only
        # announce recovery when this startup actually performed the rollback.
        if self._update_recovery.get("state")=="ROLLED_BACK" and self._update_recovery.get("recovered") is True:self.say("Alice","I restored the previous version after an interrupted update.")
        elif self._update_recovery_blocked:self.say("Alice","Update recovery needs attention. Automatic and manual package updates are disabled until recovery is checked.")
        if os.getenv("ALICE_START_HIDDEN","0").lower() in {"1","true","yes","on"}: self.root.iconify()

    def _write_startup_health(self):
        """Write a tiny post-restart health handshake for the external updater."""
        try:
            p = self.root_path / "alice_workspace" / "runtime" / "health.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"ok": True, "version": self.updates.status().get("current_version"), "started_at": time.time()}, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _schedule_auto_update_check(self):
        """Periodically check the configured stable release source.

        Installation remains governed by the UpdateService auto_install flag;
        when enabled, only a verified newer package is handed to the external
        updater, which performs the transactional install, full test suite,
        rollback on failure, and restart.
        """
        try:
            if getattr(self,"_update_recovery_blocked",False):
                self.root.after(12*60*60*1000,self._schedule_auto_update_check)
                return
            state=self.updates.status()
            if state.get("auto_check") and (state.get("repo") or state.get("feed_url")):
                threading.Thread(target=self._background_update_check,daemon=True,name="AliceAutoUpdateCheck").start()
        except Exception:
            pass
        self.root.after(12*60*60*1000, self._schedule_auto_update_check)

    def remote_mobile_setup(self):
        """Create a local pairing and display its secret once for the phone app."""
        dialog=tk.Toplevel(self.root); dialog.title("ALICE Mobile Companion"); dialog.transient(self.root); dialog.resizable(False,False)
        body=tk.Frame(dialog,padx=18,pady=16); body.pack(fill="both",expand=True)
        tk.Label(body,text="Pair a phone with ALICE",font=("Segoe UI",15,"bold")).pack(anchor="w")
        tk.Label(body,text="The pairing code contains a private key. Copy it only into your ALICE companion app.",wraplength=480,justify="left").pack(anchor="w",pady=(6,12))
        row=tk.Frame(body); row.pack(fill="x")
        tk.Label(row,text="Phone label").pack(side="left")
        label_entry=tk.Entry(row,width=32); label_entry.insert(0,"My Android phone"); label_entry.pack(side="right")
        chat_var=tk.BooleanVar(value=True); status_var=tk.BooleanVar(value=True)
        tk.Checkbutton(body,text="Allow text chat with ALICE (no computer tools)",variable=chat_var).pack(anchor="w",pady=(10,0))
        tk.Checkbutton(body,text="Allow ALICE status read",variable=status_var).pack(anchor="w")
        email_read_var=tk.BooleanVar(value=False); email_draft_var=tk.BooleanVar(value=False)
        tk.Checkbutton(body,text="Allow Gmail received-today count (requires Gmail read-only consent)",variable=email_read_var).pack(anchor="w")
        tk.Checkbutton(body,text="Allow ALICE to create local email drafts (never sends email)",variable=email_draft_var).pack(anchor="w")
        code_box=tk.Text(body,width=62,height=7,wrap="word",state="disabled")
        code_box.pack(fill="x",pady=(10,8))
        tk.Label(body,text="Private Tailscale HTTPS URL",anchor="w").pack(fill="x",pady=(4,0))
        private_url_entry=tk.Entry(body,width=62)
        private_url_entry.pack(fill="x",pady=(3,6))
        note=tk.Label(body,text="Start the health-only bridge, configure Tailscale Serve, then verify its HTTPS URL before ALICE creates a pairing secret.",wraplength=480,justify="left",fg="#555")
        note.pack(anchor="w")
        buttons=tk.Frame(body); buttons.pack(fill="x",pady=(12,0))
        prepare_button=tk.Button(buttons,text="Start local bridge")
        prepare_button.pack(side="left")
        verify_button=tk.Button(buttons,text="Verify private URL")
        verify_button.pack(side="left",padx=6)
        create_button=tk.Button(buttons,text="Create pairing code",state="disabled")
        create_button.pack(side="left")
        verified_private_url={"value":None}

        def prepare_private_bridge():
            try:
                controller=self.remote_mobile_service
                if controller is None:
                    controller=RemoteMobileServiceController(self.agent,None,port=DEFAULT_LOOPBACK_PORT,version=self._app_version())
                    address=controller.prepare()
                    write_config(self.root_path,enabled=True,port=address[1])
                    self.remote_mobile_service=controller
                else:
                    service=getattr(controller,"_service",None)
                    address=service.address if service is not None else controller.prepare()
                prepare_button.configure(state="disabled",text="Local bridge ready")
                note.configure(text=f"Health-only listener is running on {address[0]}:{address[1]}. In PowerShell run: tailscale serve --bg {address[1]}. Then paste its https://…ts.net URL above and verify it. No pairing code exists yet.")
            except Exception as exc:
                messagebox.showerror("Bridge setup failed",f"ALICE could not start the local health endpoint. Details: {type(exc).__name__}",parent=dialog)

        def verify_private_url():
            url=private_url_entry.get().strip()
            controller=self.remote_mobile_service
            if controller is None or getattr(controller,"_service",None) is None:
                messagebox.showerror("Start the local bridge first","Start the local bridge before checking the private URL.",parent=dialog); return
            verified_private_url["value"]=None
            create_button.configure(state="disabled")
            verify_button.configure(state="disabled",text="Checking…")
            def check():
                ok=verify_private_health_url(url)
                def finish():
                    if not dialog.winfo_exists():return
                    verify_button.configure(state="normal",text="Verify private URL")
                    if ok:
                        verified_private_url["value"]=url
                        create_button.configure(state="normal")
                        note.configure(text="Private HTTPS health check passed. ALICE can now create a one-time pairing code for the selected permissions.")
                    else:
                        note.configure(text="Could not verify this Tailscale HTTPS URL. Check the URL and that Tailscale Serve forwards to the local ALICE bridge.")
                        messagebox.showerror("Private URL not verified","ALICE did not receive its exact health response over trusted HTTPS. No pairing code was created.",parent=dialog)
                self.root.after(0,finish)
            threading.Thread(target=check,daemon=True,name="AliceMobileHealthCheck").start()

        prepare_button.configure(command=prepare_private_bridge)
        verify_button.configure(command=verify_private_url)

        def create_pairing():
            private_url=private_url_entry.get().strip()
            if not private_url or verified_private_url["value"]!=private_url:
                messagebox.showerror("Verify private HTTPS first","ALICE creates pairing codes only after the private Tailscale HTTPS URL passes its health check.",parent=dialog); return
            scopes=set()
            if chat_var.get():scopes.add("chat")
            if status_var.get():scopes.add("status.read")
            if email_read_var.get():scopes.add("email.read")
            if email_draft_var.get():scopes.add("email.draft")
            if not scopes:
                messagebox.showerror("Select a permission","Choose at least one permission for this phone.",parent=dialog); return
            try:
                store=DPAPIPairingStore()
                prior_clients=store.clients()
                replace_existing=bool(prior_clients)
                protected_snapshot=store.snapshot()
                if replace_existing and not messagebox.askyesno(
                        "Replace phone pairing?",
                        "Creating a new code will invalidate the current phone pairing. Continue?",
                        parent=dialog):
                    return
                grant=store.pair(label_entry.get(),scopes,replace_existing=replace_existing)
                controller=RemoteMobileServiceController(self.agent,store,port=DEFAULT_LOOPBACK_PORT,version=self._app_version(),email_service=getattr(self,"email_service",None))
                previous=self.remote_mobile_service
                if previous is not None:
                    previous.shutdown()
                    self.remote_mobile_service=None
                try:
                    address=controller.start(grant.client_id)
                    write_config(self.root_path,enabled=True,client_id=grant.client_id,port=address[1])
                except Exception:
                    controller.shutdown()
                    store.restore_snapshot(protected_snapshot)
                    if previous is not None:
                        try:
                            previous=start_configured_service(self.agent,self.root_path,version=self._app_version(),email_service=getattr(self,"email_service",None))
                            self.remote_mobile_service=previous
                        except Exception:
                            self.remote_mobile_service=None
                    raise
                self.remote_mobile_service=controller
                self.runtime.audit.record("remote_mobile_pairing_created",client_id=grant.client_id,scopes=sorted(grant.scopes))
                code=json.dumps({"v":1,"client_id":grant.client_id,"secret":grant.secret_for_pairing,"scopes":sorted(grant.scopes)},separators=(",",":"))
                code_box.configure(state="normal"); code_box.delete("1.0","end"); code_box.insert("1.0",code); code_box.configure(state="disabled")
                note.configure(text=f"Paired and listening on {address[0]}:{address[1]} only. Use the verified private URL in the phone app; computer tools are not exposed.")
                create_button.configure(state="disabled")
            except Exception as exc:
                messagebox.showerror("Pairing failed",f"ALICE could not securely create the pairing. Details: {type(exc).__name__}",parent=dialog)

        def copy_code():
            try:
                value=code_box.get("1.0","end").strip()
                if not value:return
                dialog.clipboard_clear(); dialog.clipboard_append(value); dialog.update_idletasks()
                messagebox.showinfo("Copied","Pairing code copied. Paste it only into the ALICE companion on your phone.",parent=dialog)
            except Exception:pass

        def revoke_pairing():
            store=DPAPIPairingStore()
            clients=store.clients()
            if not clients:
                messagebox.showinfo("No paired phone","There are no paired phones to revoke.",parent=dialog); return
            if not messagebox.askyesno("Revoke phone access","Revoke ALICE access for the paired phone and stop the remote bridge?",parent=dialog):return
            try:
                if self.remote_mobile_service is not None:self.remote_mobile_service.shutdown()
                self.remote_mobile_service=None
                write_config(self.root_path,enabled=False)
                for client in clients:store.revoke(client.client_id)
                self.runtime.audit.record("remote_mobile_pairing_revoked",count=len(clients))
                code_box.configure(state="normal"); code_box.delete("1.0","end"); code_box.configure(state="disabled")
                create_button.configure(state="normal")
                note.configure(text="Phone pairing revoked. The loopback bridge is stopped.")
                messagebox.showinfo("Access revoked","The paired phone key was deleted and ALICE's mobile bridge was stopped.",parent=dialog)
            except Exception as exc:
                messagebox.showerror("Revoke failed",f"ALICE could not finish revoking phone access. Details: {type(exc).__name__}",parent=dialog)

        create_button.configure(command=create_pairing)
        tk.Button(buttons,text="Copy code",command=copy_code).pack(side="left",padx=8)
        tk.Button(buttons,text="Revoke paired phone",command=revoke_pairing).pack(side="left",padx=4)
        tk.Button(buttons,text="Close",command=dialog.destroy).pack(side="right")

    def _background_update_check(self):
        try:
            state=self.updates.status()
            local=state.get("local_zip")
            if state.get("auto_install_local") and local and os.path.isfile(local) and not self._shutdown:
                info=self.updates.check_local(local)
                if info.get("available"):
                    result=self._schedule_package_upgrade(local)
                    self._queue_ui("finish", {"status":"completed","result":result.get("message","Verified local update scheduled."),"streamed":False}, threading.Event())
                    return
            info=self.updates.check()
            if not info.get("available"):
                return
            downloaded=self.updates.download(info)
            if self.updates.status().get("auto_install"):
                package=downloaded.get("package")
                if package and os.path.isfile(package) and not self._shutdown:
                    result=self._schedule_package_upgrade(package)
                    self._queue_ui("finish", {"status":"completed","result":result.get("message","Verified update scheduled."),"streamed":False}, threading.Event())
            else:
                self._queue_ui("update_check", {**info,"downloaded":True})
        except Exception as exc:
            self._queue_ui("update_check", {"ok":False,"error":str(exc)})

    def _learn_task_completed(self, payload):
        try:
            self.learning.record_runtime_action_failures(payload)
            self.learning.record_verified_recovery_outcome(payload)
            self.learning.record_verified_runtime_outcome(payload)
        except Exception:
            pass

    def _learn_task_observed(self, payload):
        try:
            if isinstance(payload.get("failure_diagnostics"),list):
                self.learning.record_runtime_action_failures(payload)
        except Exception:
            pass

    def _learn_task_failed(self, payload):
        try:
            diagnostics=self.learning.record_runtime_action_failures(payload)
            if diagnostics.get("recorded"):
                return
            request=str(payload.get("request", ""))
            source=str(payload.get("source", "runtime"))
            error=str(payload.get("error", "unknown"))
            self.learning.record(request, f"runtime:{source}", False, error=error,
                error_class="RuntimeTaskFailure",verified=False,
                evidence={"verified":False},context={"source": source,"completion_state":"failed_or_unverified"})
        except Exception:
            pass

    def _build_main_ui(self):
        from ..goals.verified_workflow import VerifiedGoalWorkflow
        self.goal_workflow=VerifiedGoalWorkflow(self.root_path,self.runtime,goals=self.goals,world=self.world)
        header=tk.Frame(self.root); header.pack(fill="x",padx=14,pady=(10,6))
        tk.Label(header,text="ALICE",font=("Segoe UI",24,"bold")).pack(side="left")
        tk.Label(header,text=f"  GLUTTONY AI  •  {self._app_version()}",font=("Segoe UI",11)).pack(side="left",pady=(10,0))
        tk.Label(header,text="● ONLINE",font=("Segoe UI",10)).pack(side="right")
        self.hud_chat_button=tk.Button(header,text="HUD CHAT",command=self.toggle_hud_chat,width=11)
        self.hud_chat_button.pack(side="right",padx=8)
        self.chat=scrolledtext.ScrolledText(self.root,wrap=tk.WORD,font=("Segoe UI",11),state="disabled",padx=12,pady=12)
        self.chat.pack(fill="both",expand=True,padx=14,pady=(0,4))
        status_row=tk.Frame(self.root); status_row.pack(fill="x",padx=16,pady=(3,0))
        self.activity=tk.Label(status_row,text=self.provider_status(),anchor="w",font=("Segoe UI",9)); self.activity.pack(side="left",fill="x",expand=True)
        self.provider_button=tk.Button(status_row,text="Provider",command=self.provider_setup,width=10); self.provider_button.pack(side="right")
        bottom=tk.Frame(self.root); bottom.pack(fill="x",padx=14,pady=(7,10))
        self.entry=tk.Entry(bottom,font=("Segoe UI",12)); self.entry.pack(side="left",fill="x",expand=True,ipady=8); self.entry.bind("<Return>",lambda e:self.send())
        self.send_button=tk.Button(bottom,text="Send",command=self.send,width=8); self.send_button.pack(side="left",padx=3)
        self.listen_button=tk.Button(bottom,text="Listen",command=self.listen,width=8); self.listen_button.pack(side="left",padx=3)
        self.stop_button=tk.Button(bottom,text="Stop",command=self.stop_current,width=7,state="disabled"); self.stop_button.pack(side="left",padx=3)
        tools=tk.Menubutton(bottom,text="Tools ▾",width=10,relief="raised")
        menu=tk.Menu(tools,tearoff=False)
        menu.add_command(label="Conversation History",command=self.show_history)
        menu.add_command(label="Goals & Tasks",command=self.show_goals)
        menu.add_command(label="Voice & Microphone",command=self.audio_center)
        menu.add_separator()
        self.text_menu_index=menu.index("end")+1
        menu.add_command(label="Text: ON",command=self.toggle_text_mode)
        self.concise_menu_index=menu.index("end")+1
        menu.add_command(label="Concise: ON",command=self.toggle_concise)
        menu.add_command(label="Read Last Response",command=self.read_last)
        menu.add_command(label="Eyes / Screen",command=self.eyes)
        menu.add_separator()
        menu.add_command(label="Approvals",command=self.show_approvals)
        menu.add_command(label="DEVOUR Review",command=self.show_devour_review)
        menu.add_command(label="Updates",command=self.update_center)
        menu.add_command(label="Provider Setup",command=self.provider_setup)
        menu.add_command(label="Mobile Companion Setup",command=self.remote_mobile_setup)
        menu.add_command(label="Premium UI Preview",command=self.open_premium_ui_preview)
        menu.add_separator()
        menu.add_command(label="Clear Visible Chat",command=self.clear_visible_chat)
        menu.add_command(label="Shutdown ALICE",command=self.shutdown)
        tools.configure(menu=menu); tools.pack(side="left",padx=3)
        self.tools_menu=menu
        from .windows_accessibility import WindowsAccessibleEntry, set_native_accessible_name
        for widget,name in ((self.provider_button,"Provider"),(self.send_button,"Send"),
                            (self.listen_button,"Listen"),(self.stop_button,"Stop"),(tools,"Tools")):
            set_native_accessible_name(widget,name)
        self._native_accessible_entry=WindowsAccessibleEntry(self.root,bottom,self.entry,self.send)
        # The old eight-button strip is intentionally replaced by this compact
        # menu so the conversation area retains maximum height on small screens.
        self.root.bind("<Configure>", lambda _e: self._schedule_window_state_save())

    def _sync_message_from_native(self):
        native=getattr(self,"_native_accessible_entry",None)
        if native is not None and native.available:
            native_value=native.get_value()
            # The native EDIT may be empty while the visible Tk Entry owns the
            # draft (for example after focus changes). Never erase a non-empty
            # draft with an empty, unfocused mirror. If the native EDIT still
            # has focus, its empty value is authoritative (including a user
            # intentionally clearing the draft).
            if native_value or native.has_focus():
                current=self.entry.get()
                if current!=native_value:
                    self.entry.delete(0,"end")
                    self.entry.insert(0,native_value)

    def _sync_message_to_native(self):
        native=getattr(self,"_native_accessible_entry",None)
        if native is not None and native.available:
            native.set_value(self.entry.get())

    def _focus_message_entry(self):
        native=getattr(self,"_native_accessible_entry",None)
        if native is not None and native.available:
            native.focus_set()
        else:
            self.entry.focus_set()

    def clear_visible_chat(self):
        self.chat.config(state="normal"); self.chat.delete("1.0","end"); self.chat.config(state="disabled")
        if self._hud_chatbox is not None: self._hud_chatbox.clear()

    def open_premium_ui_preview(self):
        """Open the supplied premium HTML mockup without pretending it is live chat."""
        import webbrowser
        preview = Path(__file__).resolve().parent / "assets" / "alice-premium-ui-preview.html"
        if not preview.is_file():
            messagebox.showerror("Premium UI preview unavailable", "The bundled preview file is missing.", parent=self.root)
            return False
        return bool(webbrowser.open(preview.as_uri()))

    def _read_hud_chat_state(self):
        try:
            data=json.loads((self.root_path/"alice_workspace"/"runtime"/"hud_chat.json").read_text(encoding="utf-8"))
            return isinstance(data,dict) and data.get("enabled") is True
        except Exception:
            return False

    def _save_hud_chat_state(self, enabled):
        path=self.root_path/"alice_workspace"/"runtime"/"hud_chat.json"
        try:
            path.parent.mkdir(parents=True,exist_ok=True)
            tmp=path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"enabled":bool(enabled)},indent=2),encoding="utf-8")
            tmp.replace(path)
        except Exception:
            pass

    def toggle_hud_chat(self):
        if self._hud_chatbox is not None and not self._hud_chatbox._closed:
            self._hud_chatbox.close()
            return
        self._open_hud_chatbox()

    def _open_hud_chatbox(self):
        if self._hud_chatbox is not None and not self._hud_chatbox._closed:
            try:self._hud_chatbox.window.lift()
            except Exception:pass
            return
        try:
            self._hud_chatbox=HUDChatbox(self.root,self._send_hud_text,self._hud_chatbox_closed,self._app_version())
            for row in self.conversation.recent(80):
                role=str(row.get("role",""))
                speaker="You" if role=="user" else "Alice" if role=="assistant" else role.title()
                self._hud_chatbox.append(speaker,row.get("content",""))
            self._hud_chat_enabled=True
            self._save_hud_chat_state(True)
            if hasattr(self,"hud_chat_button"):self.hud_chat_button.configure(text="HUD CHAT • ON")
        except Exception as exc:
            self._hud_chatbox=None
            self._hud_chat_enabled=False
            self._save_hud_chat_state(False)
            messagebox.showerror("HUD Chatbox unavailable",f"Could not open the optional HUD chat window: {type(exc).__name__}",parent=self.root)

    def _hud_chatbox_closed(self):
        self._hud_chatbox=None
        self._hud_chat_enabled=False
        self._save_hud_chat_state(False)
        if hasattr(self,"hud_chat_button"):
            try:self.hud_chat_button.configure(text="HUD CHAT")
            except Exception:pass

    def _send_hud_text(self,text):
        self._submit_text(text,source="hud")

    def show_history(self):
        win=tk.Toplevel(self.root); win.title("ALICE Conversation History"); win.geometry("900x650"); win.minsize(700,450); win.transient(self.root)
        top=tk.Frame(win); top.pack(fill="x",padx=12,pady=10)
        tk.Label(top,text="Conversation history",font=("Segoe UI",16,"bold")).pack(side="left")
        search=tk.Entry(top); search.pack(side="left",fill="x",expand=True,padx=14); search.insert(0,"")
        body=scrolledtext.ScrolledText(win,wrap=tk.WORD,font=("Segoe UI",10),state="disabled",padx=12,pady=10); body.pack(fill="both",expand=True,padx=12)
        footer=tk.Frame(win); footer.pack(fill="x",padx=12,pady=10)
        count=tk.Label(footer,text=""); count.pack(side="left")
        def render(*_):
            needle=search.get().strip().lower(); rows=self.conversation.all(); shown=[]
            for row in rows:
                content=str(row.get("content","")); role=str(row.get("role",""));
                if needle and needle not in content.lower(): continue
                stamp=time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(float(row.get("time",0))))
                label="You" if role=="user" else "Alice" if role=="assistant" else role.title()
                shown.append(f"[{stamp}] {label}:\n{content}\n\n")
            body.config(state="normal"); body.delete("1.0","end"); body.insert("end","".join(shown)); body.config(state="disabled"); body.see("end")
            count.config(text=f"Showing {len(shown)} of {len(rows)} stored turns")
        search.bind("<KeyRelease>",render)
        tk.Button(footer,text="Refresh",command=render,width=10).pack(side="right",padx=4)
        tk.Button(footer,text="Close",command=win.destroy,width=10).pack(side="right",padx=4)
        render()

    def show_goals(self):
        """Open persistent goals with a clear, explicit approval before execution."""
        existing=getattr(self,"_goal_window",None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.deiconify(); existing.lift(); self._refresh_goal_view(); return
            except Exception:
                pass
        win=tk.Toplevel(self.root); win.title("ALICE Goals & Tasks"); win.geometry("920x560"); win.minsize(700,420); win.transient(self.root)
        self._goal_window=win
        body=tk.Frame(win); body.pack(fill="both",expand=True,padx=12,pady=12)
        left=tk.Frame(body); left.pack(side="left",fill="both",expand=True,padx=(0,8))
        right=tk.Frame(body); right.pack(side="left",fill="both",expand=True,padx=(8,0))
        tk.Label(left,text="Goals",font=("Segoe UI",12,"bold")).pack(anchor="w")
        goal_tree=ttk.Treeview(left,columns=("status","steps"),show="tree headings",selectmode="browse")
        goal_tree.heading("#0",text="Goal"); goal_tree.heading("status",text="Status"); goal_tree.heading("steps",text="Steps")
        goal_tree.column("#0",width=260,stretch=True); goal_tree.column("status",width=90,stretch=False); goal_tree.column("steps",width=70,stretch=False)
        goal_tree.pack(fill="both",expand=True,pady=(4,8))
        tk.Label(right,text="Steps",font=("Segoe UI",12,"bold")).pack(anchor="w")
        step_tree=ttk.Treeview(right,columns=("status","ready"),show="tree headings",selectmode="browse")
        step_tree.heading("#0",text="Step"); step_tree.heading("status",text="Status"); step_tree.heading("ready",text="Ready")
        step_tree.column("#0",width=250,stretch=True); step_tree.column("status",width=90,stretch=False); step_tree.column("ready",width=70,stretch=False)
        step_tree.pack(fill="both",expand=True,pady=(4,8))
        self._goal_tree=goal_tree; self._goal_step_tree=step_tree
        goal_tree.bind("<<TreeviewSelect>>",lambda _event:self._refresh_goal_steps())
        controls=tk.Frame(win); controls.pack(fill="x",padx=12,pady=(0,12))
        tk.Button(controls,text="New Goal",command=self._create_goal_dialog).pack(side="left",padx=3)
        tk.Button(controls,text="Add Step",command=self._add_goal_step_dialog).pack(side="left",padx=3)
        tk.Button(controls,text="Run Selected Step",command=self._confirm_run_goal_step).pack(side="left",padx=3)
        tk.Button(controls,text="Pause / Resume",command=self._toggle_selected_goal).pack(side="left",padx=3)
        tk.Button(controls,text="Refresh",command=self._refresh_goal_view).pack(side="right",padx=3)
        tk.Button(controls,text="Close",command=win.destroy).pack(side="right",padx=3)
        win.protocol("WM_DELETE_WINDOW",win.destroy)
        self._refresh_goal_view()

    def _selected_goal_id(self):
        tree=getattr(self,"_goal_tree",None)
        selected=tree.selection() if tree is not None else ()
        return selected[0] if selected else None

    def _selected_goal_step_id(self):
        tree=getattr(self,"_goal_step_tree",None)
        selected=tree.selection() if tree is not None else ()
        return selected[0] if selected else None

    def _refresh_goal_view(self):
        tree=getattr(self,"_goal_tree",None)
        if tree is None or not tree.winfo_exists(): return
        selected=self._selected_goal_id()
        for item in tree.get_children(): tree.delete(item)
        for goal in self.goals.data.get("goals",[]):
            steps=goal.get("steps",[])
            completed=sum(step.get("status")=="completed" for step in steps)
            tree.insert("","end",iid=goal["id"],text=goal.get("title","(untitled)"),
                        values=(goal.get("status","unknown"),f"{completed}/{len(steps)}"))
        if selected and tree.exists(selected): tree.selection_set(selected)
        elif tree.get_children(): tree.selection_set(tree.get_children()[0])
        self._refresh_goal_steps()

    def _refresh_goal_steps(self):
        goals_tree=getattr(self,"_goal_tree",None); steps_tree=getattr(self,"_goal_step_tree",None)
        if goals_tree is None or steps_tree is None or not steps_tree.winfo_exists(): return
        for item in steps_tree.get_children(): steps_tree.delete(item)
        gid=self._selected_goal_id()
        if not gid: return
        try: goal=self.goals.status(gid)["goal"]
        except (KeyError,ValueError): return
        ready={step["id"] for step in self.goals.ready_steps(gid)}
        for step in goal.get("steps",[]):
            steps_tree.insert("","end",iid=step["id"],text=step.get("title","(untitled)"),
                              values=(step.get("status","unknown"),"yes" if step["id"] in ready else "no"))

    def _create_goal_dialog(self):
        dialog=tk.Toplevel(self._goal_window); dialog.title("New Goal")
        dialog.geometry("520x250"); dialog.resizable(False,False); dialog.transient(self._goal_window)
        dialog.grab_set()
        form=tk.Frame(dialog); form.pack(fill="both",expand=True,padx=18,pady=16)
        tk.Label(form,text="Goal title").pack(anchor="w")
        title_anchor=tk.Entry(form,font=("Segoe UI",11)); title_anchor.pack(fill="x",pady=(4,12),ipady=4)
        tk.Label(form,text="Goal objective").pack(anchor="w")
        objective_anchor=tk.Entry(form,font=("Segoe UI",11)); objective_anchor.pack(fill="x",pady=(4,12),ipady=4)
        from .windows_accessibility import WindowsAccessibleEntry, set_native_accessible_name
        native_fields={}

        def field_value(name,anchor):
            native=native_fields.get(name)
            return native.get_value() if native is not None and native.available else anchor.get()

        def close_dialog():
            for native in native_fields.values():
                try:native.close()
                except Exception:pass
            try:dialog.grab_release()
            except Exception:pass
            try:dialog.destroy()
            except Exception:pass

        def save_goal():
            title=field_value("title",title_anchor).strip()
            objective=field_value("objective",objective_anchor).strip()
            if not title or not objective:
                messagebox.showerror("Goal not saved","Enter both a title and an objective.",parent=dialog)
                return
            try:
                goal=self.goals.create(title,objective)
                self._refresh_goal_view()
                if self._goal_tree.exists(goal["id"]):self._goal_tree.selection_set(goal["id"])
            except Exception as exc:
                messagebox.showerror("Goal not saved",str(exc),parent=dialog)
                return
            close_dialog()

        buttons=tk.Frame(form); buttons.pack(fill="x",side="bottom",pady=(4,0))
        cancel_button=tk.Button(buttons,text="Cancel",command=close_dialog,width=10)
        cancel_button.pack(side="right",padx=(6,0))
        create_button=tk.Button(buttons,text="Create Goal",command=save_goal,width=12)
        create_button.pack(side="right")
        set_native_accessible_name(cancel_button,"Cancel")
        set_native_accessible_name(create_button,"Create Goal")
        native_fields["title"]=WindowsAccessibleEntry(
            dialog,form,title_anchor,lambda:native_fields.get("objective") and native_fields["objective"].focus_set(),
            accessible_label="Goal title:")
        native_fields["objective"]=WindowsAccessibleEntry(
            dialog,form,objective_anchor,save_goal,accessible_label="Goal objective:")
        dialog.protocol("WM_DELETE_WINDOW",close_dialog)
        if native_fields["title"].available:native_fields["title"].focus_set()
        else:title_anchor.focus_set()

    def _add_goal_step_dialog(self):
        gid=self._selected_goal_id()
        if not gid:
            messagebox.showinfo("Select a goal","Select a goal before adding a step.",parent=self._goal_window); return
        title=simpledialog.askstring("Add Goal Step","Step title:",parent=self._goal_window)
        if not title or not title.strip(): return
        request=simpledialog.askstring("Add Goal Step","Exact request ALICE should perform for this step:",parent=self._goal_window)
        if not request or not request.strip(): return
        try:
            self.goals.add_step(gid,title.strip(),request=request.strip())
            self._refresh_goal_view()
        except Exception as exc: messagebox.showerror("Step not saved",str(exc),parent=self._goal_window)

    def _toggle_selected_goal(self):
        gid=self._selected_goal_id()
        if not gid: return
        try:
            goal=self.goals.status(gid)["goal"]
            if goal["status"]=="active":
                if any(step.get("status")=="running" for step in goal.get("steps",[])):
                    messagebox.showinfo("Goal step running","Wait for the running step to finish before pausing this goal.",parent=self._goal_window); return
                self.goals.pause(gid)
            elif goal["status"]=="paused": self.goals.resume(gid)
            else:
                messagebox.showinfo("Goal status",f"This goal is {goal['status']} and cannot be paused or resumed.",parent=self._goal_window)
            self._refresh_goal_view()
        except Exception as exc: messagebox.showerror("Goal update failed",str(exc),parent=self._goal_window)

    def _confirm_run_goal_step(self):
        gid=self._selected_goal_id(); sid=self._selected_goal_step_id()
        if not gid or not sid:
            messagebox.showinfo("Select a step","Select a goal step to run.",parent=self._goal_window); return
        try: step=self.goals.get_step(gid,sid)
        except Exception as exc:
            messagebox.showerror("Step unavailable",str(exc),parent=self._goal_window); return
        ready={row["id"] for row in self.goals.ready_steps(gid)}
        if step.get("status")!="pending" or sid not in ready:
            messagebox.showinfo("Step not ready","Only a pending step whose dependencies are complete can run.",parent=self._goal_window); return
        request=str(step.get("request") or step.get("title") or "").strip()
        if not request: return
        approved=messagebox.askyesno("Approve goal step",
            "Run this exact request through ALICE now?\n\n"+request+
            "\n\nALICE will mark the step complete only if its independent postcondition verifier passes.",
            parent=self._goal_window)
        if not approved: return
        if getattr(self,"_goal_run_busy",False):
            messagebox.showinfo("Goal step running","Wait for the current goal step to finish.",parent=self._goal_window); return
        self._goal_run_busy=True; self.activity.config(text="Running approved goal step…")
        def work():
            try: result=self.goal_workflow.run_step(gid,sid,user_approved=True)
            except Exception as exc: result={"status":"error","verified":False,"error":str(exc)}
            self._queue_ui("goal_run_complete",gid,sid,result)
        threading.Thread(target=work,daemon=True,name="AliceVerifiedGoalStep").start()

    def _apply_goal_run_complete(self,gid,sid,result):
        self._goal_run_busy=False; self.activity.config(text=self.provider_status()); self._refresh_goal_view()
        status=result.get("status","unknown")
        if status=="completed" and result.get("verified") is True:
            message=f"Goal step verified and completed.\n\nGoal: {gid}\nStep: {sid}"
        elif status in {"awaiting_approval","queued"}:
            message="The step did not run. ALICE is waiting for a separate approval."
        else:
            reason=result.get("reason") or result.get("error") or result.get("error_class") or "Independent postcondition did not pass."
            message=f"Goal step was not completed as verified.\n\nStatus: {status}\nReason: {reason}"
        window=getattr(self,"_goal_window",None)
        parent=window if window is not None and window.winfo_exists() else self.root
        messagebox.showinfo("Goal step result",message,parent=parent)

    def show_devour_review(self):
        existing=getattr(self,"_devour_review_window",None)
        if existing is not None:
            try:
                if existing.winfo_exists(): existing.deiconify(); existing.lift(); self._refresh_devour_review(); return
            except Exception: pass
        report=self.devour_reviews.latest_report_path()
        if report is None:
            messagebox.showinfo("DEVOUR Review","No valid single-source or multi-source DEVOUR analysis is available yet.",parent=self.root); return
        try: state=self.devour_reviews.inspect(report)
        except Exception as exc:
            messagebox.showerror("DEVOUR report unavailable",str(exc),parent=self.root); return
        win=tk.Toplevel(self.root); win.title("ALICE DEVOUR Review"); win.geometry("900x590"); win.minsize(700,440); win.transient(self.root)
        self._devour_review_window=win; self._devour_review_path=state["report"]
        license_info=state["license"]; security=state["security"]
        source_count=len(state.get("source_trees",[]))
        summary=(f"Source: {state['source_label'] or '(unknown)'}    License: {license_info.get('kind','unknown')}"
                 f"    Static findings: {security.get('threat_count',0)} / {security.get('files_scanned',0)} files\n"
                 +(f"Compared sources: {source_count}    Per-source dependencies, tests, manifests, and static compatibility signals are shown below.\n"
                   if state.get("multi_source") else "")
                 +self._devour_coverage_summary(state)+"\n"
                 +"Review and approve one capability at a time. Approval allows native candidate generation only; it does not execute quarantined code or install the candidate.")
        tk.Label(win,text=summary,wraplength=860,justify="left",anchor="w").pack(fill="x",padx=14,pady=(14,8))
        if license_info.get("review_required") or security.get("threat_count",0):
            tk.Label(win,text="Review warning: license review or static security findings are present. Findings are heuristics, not a malware verdict.",
                     wraplength=860,justify="left",fg="#8a3b00").pack(fill="x",padx=14,pady=(0,8))
        tree=ttk.Treeview(win,columns=("score","recommendation","approval"),show="tree headings",selectmode="browse")
        tree.heading("#0",text="Capability"); tree.heading("score",text="Evidence score")
        tree.heading("recommendation",text="Native review"); tree.heading("approval",text="Approval")
        tree.column("#0",width=240,stretch=True); tree.column("score",width=110,stretch=False)
        tree.column("recommendation",width=220,stretch=True); tree.column("approval",width=110,stretch=False)
        tree.pack(fill="both",expand=True,padx=14,pady=8)
        self._devour_review_tree=tree
        detail=tk.Text(win,height=5,wrap="word",state="disabled"); detail.pack(fill="x",padx=14,pady=(0,8))
        self._devour_review_detail=detail
        tree.bind("<<TreeviewSelect>>",lambda _event:self._show_devour_capability_detail())
        buttons=tk.Frame(win); buttons.pack(fill="x",padx=14,pady=(0,14))
        tk.Button(buttons,text="Source Inventory / Functions",command=self._show_devour_inventory).pack(side="left",padx=3)
        tk.Button(buttons,text="Approve This Capability",command=self._approve_devour_capability).pack(side="left",padx=3)
        tk.Button(buttons,text="Revoke Approval",command=self._revoke_devour_capability).pack(side="left",padx=3)
        tk.Button(buttons,text="Build Native Candidate",command=self._build_approved_devour_candidate).pack(side="left",padx=3)
        tk.Button(buttons,text="Refresh",command=self._refresh_devour_review).pack(side="right",padx=3)
        tk.Button(buttons,text="Close",command=win.destroy).pack(side="right",padx=3)
        self._refresh_devour_review()

    @staticmethod
    def _devour_coverage_summary(state):
        architecture=state.get("architecture",{}) if isinstance(state,dict) else {}
        coverage=architecture.get("file_analysis_coverage",{}) if isinstance(architecture,dict) else {}
        if coverage:
            counts=coverage.get("parser_counts",{})
            parsed=sum(value for key,value in counts.items() if key in {"static_source_candidate","java_bytecode_static"})
            opaque=sum(value for key,value in counts.items() if str(key).startswith("metadata_only"))
            return f"Static-readable inputs: {parsed}; metadata-only inputs: {opaque}; total inventoried: {coverage.get('total_files',0)}."
        details=state.get("source_details",[]) if isinstance(state,dict) else []
        if details:
            total=sum(int(row.get("file_count") or 0) for row in details)
            return f"Compared-source file count: {total}; open Source Inventory for file-level parser coverage."
        return ""

    def _show_devour_inventory(self):
        report=getattr(self,"_devour_review_path",None)
        if not report: return
        try: state=self.devour_reviews.inspect(report)
        except Exception as exc:
            messagebox.showerror("DEVOUR inventory unavailable",str(exc),parent=self._devour_review_window); return
        files=[]; modules=[]
        if state.get("multi_source"):
            for index,child in sorted(state.get("child_by_index",{}).items()):
                architecture=child.get("architecture",{}) if isinstance(child,dict) else {}
                prefix=f"source_{int(index):02d}/"
                files.extend({**row,"path":prefix+str(row.get("path",""))} for row in architecture.get("file_catalog",[]))
                modules.extend({**row,"path":prefix+str(row.get("path",""))} for row in architecture.get("modules",[]))
        else:
            architecture=state.get("architecture",{})
            files=architecture.get("file_catalog",[])
            modules=architecture.get("modules",[])
        win=tk.Toplevel(self._devour_review_window); win.title("DEVOUR Source Inventory"); win.geometry("1050x620"); win.minsize(760,420)
        tk.Label(win,text=("Fingerprints and static findings for quarantined files. Metadata-only files have no content adapter; no imported code was run."),
                 anchor="w",justify="left",wraplength=1010).pack(fill="x",padx=12,pady=8)
        tree=ttk.Treeview(win,columns=("type","size","parser","sha"),show="tree headings",selectmode="browse")
        tree.heading("#0",text="Quarantined file"); tree.heading("type",text="Type")
        tree.heading("size",text="Bytes"); tree.heading("parser",text="Inspection")
        tree.heading("sha",text="SHA-256")
        tree.column("#0",width=400,stretch=True); tree.column("type",width=100,stretch=False)
        tree.column("size",width=85,stretch=False); tree.column("parser",width=230,stretch=True)
        tree.column("sha",width=190,stretch=False)
        tree.pack(fill="both",expand=True,padx=12,pady=(0,5))
        by_path={row.get("path"):row for row in modules if isinstance(row,dict)}
        for index,row in enumerate(files):
            path=str(row.get("path","")); module=by_path.get(path,{})
            symbols=module.get("symbol_names",[])
            if module.get("methods"):
                symbols=[{"name":item.get("name"),"descriptor":item.get("descriptor")} for item in module["methods"]]
            label=(f"; symbols: {', '.join(str(item.get('name','')) for item in symbols[:6])}"
                   if symbols else "")
            tree.insert("","end",iid=f"file-{index}",text=path,
                        values=(row.get("ext") or "[none]",row.get("size",0),row.get("parser","unknown"),
                                str(row.get("sha256",""))[:16]+"…"+label))
        detail=tk.Text(win,height=5,wrap="word",state="disabled"); detail.pack(fill="x",padx=12,pady=(0,10))
        def show_symbols(_event=None):
            selection=tree.selection()
            path=tree.item(selection[0],"text") if selection else ""
            module=by_path.get(path,{})
            symbols=module.get("symbol_names",[])
            if module.get("methods"):
                symbols=module.get("methods",[])
            lines=[f"Static declarations for {path}:"]
            lines.extend(f"{item.get('kind','method')} {item.get('name','')} {item.get('descriptor','')} (line {item.get('line','?')})".strip()
                         for item in symbols[:200])
            if not symbols: lines.append("No symbol adapter result is available for this file; use its digest/type as metadata only.")
            detail.config(state="normal"); detail.delete("1.0","end"); detail.insert("end","\n".join(lines)); detail.config(state="disabled")
        tree.bind("<<TreeviewSelect>>",show_symbols)
        if tree.get_children():
            tree.selection_set(tree.get_children()[0]); show_symbols()

    def _refresh_devour_review(self):
        tree=getattr(self,"_devour_review_tree",None)
        if tree is None or not tree.winfo_exists(): return
        try: state=self.devour_reviews.inspect(self._devour_review_path)
        except Exception as exc:
            messagebox.showerror("DEVOUR report changed",str(exc),parent=self._devour_review_window); return
        selected=tree.selection()[0] if tree.selection() else None
        for item in tree.get_children(): tree.delete(item)
        for row in state["capabilities"]:
            tree.insert("","end",iid=row["name"],text=row["name"],
                        values=(str(row.get("evidence_score",0)),row.get("recommendation","manual_review"),
                                "approved" if row.get("approved") else "not approved"))
        if selected and tree.exists(selected): tree.selection_set(selected)
        elif tree.get_children(): tree.selection_set(tree.get_children()[0])
        self._show_devour_capability_detail()

    def _show_devour_capability_detail(self):
        detail=getattr(self,"_devour_review_detail",None); tree=getattr(self,"_devour_review_tree",None)
        if detail is None or tree is None or not detail.winfo_exists(): return
        selected=tree.selection(); name=selected[0] if selected else None
        rows=[]
        try: state=self.devour_reviews.inspect(self._devour_review_path)
        except Exception: state={"capabilities":[]}
        row=next((item for item in state["capabilities"] if item["name"]==name),None)
        if row:
            rows=[f"Capability: {name}",f"Recommendation: {row.get('recommendation','manual review')}",
                  f"Review decision: {row.get('decision') or 'not approved yet'}",
                  "Evidence terms: "+", ".join(map(str,row.get("evidence_terms",[])[:12])),
                  "Evidence files: "+", ".join(map(str,row.get("evidence_files",[])[:12])),
                  ("Approval is bound to this exact aggregate report and every source tree digest."
                   if state.get("multi_source") else "Approval is bound to this exact report and source tree digest.")]
            if not state.get("multi_source"):
                modules={item.get("path"):item for item in state.get("architecture",{}).get("modules",[])
                         if isinstance(item,dict)}
                symbol_lines=[]
                for evidence_path in row.get("evidence_files",[])[:8]:
                    module=modules.get(evidence_path,{})
                    symbols=module.get("symbol_names",[])
                    methods=module.get("methods",[])
                    names=[str(item.get("name","")) for item in symbols[:12]]
                    names.extend(str(item.get("name","")) for item in methods[:12])
                    if names: symbol_lines.append(f"{evidence_path}: "+", ".join(names[:16]))
                if symbol_lines: rows.append("Static functions/classes on evidence files: "+"; ".join(symbol_lines))
            if state.get("multi_source"):
                details={item["source_index"]:item for item in state.get("source_details",[])}
                rows.append("Evidence sources: "+", ".join(
                    f"{source.get('source_label','source')} (tree {str(source.get('tree_sha256',''))[:12]})"
                    for source in row.get("sources",[])))
                for source in row.get("sources",[])[:8]:
                    detail=details.get(source.get("source_index"),{})
                    quality=detail.get("source_quality",{})
                    dependencies=detail.get("dependencies",[])
                    dep_summary=", ".join(f"{dep.get('ecosystem')}:{dep.get('name')} {dep.get('specification','')}"
                        for dep in dependencies[:8] if isinstance(dep,dict)) or "no parsed manifest dependencies"
                    rows.append(f"Source {source.get('source_index')}: {detail.get('source_label','source')}; "
                        f"{len(dependencies)} declared dependencies; {quality.get('test_file_count',0)} tests; "
                        f"static score {quality.get('static_quality_score','n/a')}; dependencies: {dep_summary}")
        detail.config(state="normal"); detail.delete("1.0","end"); detail.insert("end","\n".join(rows)); detail.config(state="disabled")

    def _selected_devour_capability(self):
        tree=getattr(self,"_devour_review_tree",None)
        selected=tree.selection() if tree is not None else ()
        return selected[0] if selected else None

    def _approve_devour_capability(self):
        name=self._selected_devour_capability()
        if not name:
            messagebox.showinfo("Select a capability","Select exactly one capability to approve.",parent=self._devour_review_window); return
        try: state=self.devour_reviews.inspect(self._devour_review_path)
        except Exception as exc:
            messagebox.showerror("DEVOUR report changed",str(exc),parent=self._devour_review_window); return
        row=next((item for item in state["capabilities"] if item["name"]==name),None)
        if row is None: return
        if row["approved"]:
            messagebox.showinfo("Already approved",f"{name} is already individually approved for this report.",parent=self._devour_review_window); return
        license_info=state["license"]; security=state["security"]
        warning=(f"License review required: {license_info.get('kind','unknown')}.\n" if license_info.get("review_required") else "")
        if security.get("threat_count",0): warning+=f"Static security findings: {security['threat_count']}. These are heuristics, not a malware verdict.\n"
        decision=simpledialog.askstring("Per-capability DEVOUR decision",
            "Choose one decision for this capability:\n"
            "reuse_compatible_component = use an already verified ALICE component; no candidate package\n"
            "integrate_behind_alice_interface = generate and test ALICE-owned integration code\n"
            "implement_native_equivalent = generate and test a native ALICE equivalent",
            initialvalue="implement_native_equivalent",parent=self._devour_review_window)
        if decision is None: return
        decision=" ".join(decision.strip().lower().split())
        architecture=state.get("architecture",{})
        ui_files={".html",".css",".scss",".sass",".less",".vue",".svelte",".tsx",".jsx"}
        has_ui=any(str(item.get("ext","")).casefold() in ui_files
                   for item in architecture.get("file_catalog",[]))
        has_ui=has_ui or bool({"frontend","front-end","user interface","ui","theme","dashboard","stylesheet"}
                              & {str(term).casefold() for term in row.get("evidence_terms",[])})
        ui_request=""
        if has_ui and messagebox.askyesno("Adapt ALICE's UI?",
                "This source appears to include a user interface. Do you want ALICE to create an ALICE-native UI adaptation?\n\n"
                "If yes, describe the appearance or behavior you want. The source UI will not replace ALICE automatically.",
                parent=self._devour_review_window):
            ui_request=simpledialog.askstring("Describe your UI adaptation",
                "What should ALICE's adapted interface look or behave like? (up to 1000 characters)",
                parent=self._devour_review_window)
            if ui_request is None: return
            ui_request=" ".join(ui_request.split())
            if not ui_request or len(ui_request)>1000:
                messagebox.showinfo("UI request needed","Enter a non-empty UI request of at most 1000 characters.",parent=self._devour_review_window); return
            if decision=="reuse_compatible_component":
                messagebox.showinfo("Choose an integration decision",
                    "A UI adaptation creates ALICE-owned code. Choose integrate_behind_alice_interface or implement_native_equivalent.",
                    parent=self._devour_review_window); return
        approved=messagebox.askyesno("Approve one DEVOUR capability",
            f"Record '{decision}' for only '{name}'?\n\n"
            +(f"User-requested UI adaptation: {ui_request}\n\n" if ui_request else "")
            +f"{warning}"
            "The source remains quarantined. This does not activate the source, create an update, or install anything.",
            parent=self._devour_review_window)
        if not approved: return
        try:
            self.devour_reviews.approve_capability(self._devour_review_path,name,confirmed=True,
                                                   decision=decision,ui_request=ui_request)
            self._refresh_devour_review()
        except Exception as exc: messagebox.showerror("Approval not saved",str(exc),parent=self._devour_review_window)

    def _revoke_devour_capability(self):
        name=self._selected_devour_capability()
        if not name: return
        try: state=self.devour_reviews.inspect(self._devour_review_path)
        except Exception as exc:
            messagebox.showerror("DEVOUR report changed",str(exc),parent=self._devour_review_window); return
        row=next((item for item in state["capabilities"] if item["name"]==name),None)
        if not row or not row["approved"]: return
        if not messagebox.askyesno("Revoke DEVOUR approval",f"Revoke the current approval for '{name}'?",parent=self._devour_review_window): return
        try:
            self.devour_reviews.revoke_capability(self._devour_review_path,name,confirmed=True)
            self._refresh_devour_review()
        except Exception as exc: messagebox.showerror("Revocation not saved",str(exc),parent=self._devour_review_window)

    def _build_approved_devour_candidate(self):
        name=self._selected_devour_capability()
        if not name: return
        if getattr(self,"_devour_build_busy",False):
            messagebox.showinfo("Candidate in progress","Wait for the current DEVOUR candidate build to finish.",parent=self._devour_review_window); return
        try: evidence=self.devour_reviews.approval_evidence(self._devour_review_path,[name])
        except Exception as exc:
            messagebox.showerror("Capability not approved",str(exc),parent=self._devour_review_window); return
        decision=evidence.get("decisions",{}).get(name,"implement_native_equivalent")
        ui_request=evidence.get("ui_requests",{}).get(name,"")
        if decision=="reuse_compatible_component":
            messagebox.showinfo("Existing ALICE component selected",
                f"'{name}' is marked to reuse an existing ALICE component. No candidate package is needed or will be built.",
                parent=self._devour_review_window); return
        if not messagebox.askyesno("Build native candidate",
            f"Build and test an ALICE-owned candidate for this approved capability?\n\n{name}\nDecision: {decision}\n\n"
            "The candidate will remain separate from the running ALICE installation. A second decision is required before installation.",
            parent=self._devour_review_window): return
        report=self._devour_review_path; self._devour_build_busy=True; self.activity.config(text="Building approved DEVOUR candidate…")
        def work():
            try:
                task=f"Apply only the individually approved decision '{decision}' for capability: {name}"
                if ui_request:
                    task+=f". Create an ALICE-native UI adaptation guided by this user-approved request: {ui_request}"
                result=self.devour.self_manager.prepare_devour_upgrade(
                    task,report,
                    approved_capabilities=[name])
            except Exception as exc: result={"ok":False,"status":"failed","error":str(exc)}
            self._queue_ui("devour_candidate_complete",report,name,result)
        threading.Thread(target=work,daemon=True,name="AliceDevourCandidate").start()

    def _apply_devour_candidate_complete(self,report,name,result):
        self._devour_build_busy=False; self.activity.config(text=self.provider_status())
        if not result.get("ok"):
            messagebox.showerror("DEVOUR candidate failed",str(result.get("error","unknown candidate failure")),parent=self.root); return
        package=result.get("package",{}); package_path=package.get("package") if isinstance(package,dict) else None
        if not package_path:
            messagebox.showerror("DEVOUR candidate incomplete","The candidate did not produce a package path.",parent=self.root); return
        receipts=result.get("capability_evidence",[])
        receipt=next((row for row in receipts if isinstance(row,dict) and row.get("name")==name),None)
        if (not receipt or receipt.get("recorded") is not True or receipt.get("active") is not False
                or receipt.get("verified") is not False or receipt.get("candidate_sha256")!=package.get("sha256")):
            messagebox.showerror("Candidate evidence missing",
                "The candidate was preserved, but its approval and test evidence was not durably recorded in the capability registry. Installation is blocked.",
                parent=self.root); return
        status=result.get("status","unknown")
        version=package.get("version","unknown") if isinstance(package,dict) else "unknown"
        if status!="tested_candidate_isolated_pending_review":
            messagebox.showinfo("Candidate preserved",
                f"ALICE-native candidate {version} was packaged but did not prove isolated candidate execution. It cannot be installed.\n\n"
                f"Path: {package_path}\nCapability: {name}\nCapability registry: evidence saved; capability remains unavailable.",parent=self.root); return
        try:
            from ..deployment.updater import InPlaceUpdater
            manifest=InPlaceUpdater(self.root_path).validate_package(package_path)["manifest"]
            provenance=manifest.get("provenance",{})
            sandbox=provenance.get("verification",{}).get("sandbox",{})
            changed=package.get("changed",[])
            if sandbox.get("verified") is not True:
                raise ValueError("candidate package lacks verified OS-level isolation evidence")
        except Exception as exc:
            messagebox.showerror("Candidate verification failed",str(exc),parent=self.root); return
        install=messagebox.askyesno("Install reviewed DEVOUR candidate",
            f"Install ALICE {version} with the individually approved native capability '{name}'?\n\n"
            f"Changed files: {', '.join(map(str,changed[:12])) or '(see package manifest)'}\n"
            "The capability evidence is saved as a candidate, not active or runtime-verified. The external updater creates a rollback backup, runs the full test suite, and restores the prior version if a gate fails.\n\n"
            "Install this candidate now?",parent=self.root)
        if install:
            try:
                scheduled=self._schedule_package_upgrade(package_path)
                self.say("Alice",scheduled.get("message","Verified native candidate installation was scheduled."))
            except Exception as exc: messagebox.showerror("Candidate not scheduled",str(exc),parent=self.root)
        else:
            messagebox.showinfo("Candidate preserved",f"No installation was scheduled. Candidate remains at:\n{package_path}",parent=self.root)

    def _build_floating_indicator(self):
        """Create a static frosted Mini ALICE pill; animate only while active."""
        self._bubble_width=300; self._bubble_height=62; self._bubble_size=self._bubble_width
        self._bubble_key_color="#ff00ff"; self._mini_mode_active=False
        self._mini_compact=False; self._mini_status="READY"; self._mini_transcript="Ready when you are."
        self._mini_response_pending=False; self._mini_compact_after=None; self._mini_click_after=None; self._mini_ignore_release=False
        self._orb_state="idle"; self._orb_phase=0.0; self._mini_drop_hooks=[]
        self.bubble=tk.Toplevel(self.root); self.bubble.overrideredirect(True); self.bubble.attributes("-topmost",True); self.bubble.configure(bg=self._bubble_key_color)
        try:self.bubble.wm_attributes("-transparentcolor",self._bubble_key_color)
        except tk.TclError:self._bubble_key_color="#111111"; self.bubble.configure(bg=self._bubble_key_color)
        try:self.bubble.attributes("-alpha",0.96)
        except tk.TclError:pass
        self._restore_bubble_position()
        canvas=tk.Canvas(self.bubble,width=self._bubble_width,height=self._bubble_height,bg=self._bubble_key_color,highlightthickness=0,cursor="hand2"); canvas.pack()
        self._orb_canvas=canvas
        self._mini_bg=canvas.create_polygon(5,5,self._bubble_width-5,5,self._bubble_width-5,self._bubble_height-5,5,self._bubble_height-5,
            smooth=True,fill="#111a12",outline="#8dc63f",width=1)
        canvas.create_oval(15,17,45,47,fill="#1e3218",outline="#8dc63f",width=1)
        canvas.create_text(30,32,text="A",fill="#e7f6d3",font=("Segoe UI",14,"bold"))
        self._mini_status_id=canvas.create_text(55,24,anchor="w",text=self._mini_status,fill="#c8ec9c",font=("Segoe UI",8,"bold"))
        self._mini_transcript_id=canvas.create_text(55,41,anchor="w",width=190,text=self._mini_transcript,fill="#edf3e7",font=("Segoe UI",9))
        self._mini_wave_ids=[]
        for i,h in enumerate((7,12,9,15,8)):
            x=251+i*6
            self._mini_wave_ids.append(canvas.create_line(x,32-h/2,x,32+h/2,fill="#8dc63f",width=2,capstyle="round"))
        canvas.create_text(282,32,text="↗",fill="#d6efbd",font=("Segoe UI",12,"bold"))
        canvas.bind("<Button-1>",self._bubble_press); canvas.bind("<B1-Motion>",self._bubble_drag_move); canvas.bind("<ButtonRelease-1>",self._bubble_release); canvas.bind("<Double-Button-1>",self._bubble_double_click)
        self.bubble.bind("<Button-3>",self._show_bubble_menu)
        self._bubble_menu=tk.Menu(self.bubble,tearoff=False)
        self._bubble_menu.add_command(label="Show / Hide ALICE",command=self.toggle_window); self._bubble_menu.add_separator()
        self._bubble_menu.add_command(label="Voice & Microphone",command=self.audio_center); self._bubble_menu.add_command(label="Text: ON",command=self.toggle_text_mode); self._bubble_menu.add_command(label="Concise: ON",command=self.toggle_concise); self._bubble_menu.add_command(label="Read Last Response",command=self.read_last); self._bubble_menu.add_command(label="Eyes / Screen",command=self.eyes); self._bubble_menu.add_separator()
        self._bubble_menu.add_command(label="Maximize / Restore",command=self.toggle_maximize); self._bubble_menu.add_command(label="Fullscreen",command=self.toggle_fullscreen); self._bubble_menu.add_separator()
        self._bubble_menu.add_command(label="Approvals",command=self.show_approvals); self._bubble_menu.add_command(label="Updates",command=self.update_center); self._bubble_menu.add_command(label="Provider Setup",command=self.provider_setup); self._bubble_menu.add_command(label="Clear Visible Chat",command=self.clear_visible_chat); self._bubble_menu.add_separator(); self._bubble_menu.add_command(label="Shutdown ALICE",command=self.shutdown)
        try:
            from .win_drop import register_file_drop
            def dropped(paths): self._queue_ui("mini_file_dropped",paths)
            for widget in (self.bubble,canvas):
                hook=register_file_drop(widget.winfo_id(),dropped)
                if hook:self._mini_drop_hooks.append(hook)
        except Exception:pass
        self._animate_orb_bubble()
        self.bubble.withdraw()

    def _start_tray_icon(self):
        """Keep a tiny Windows notification-area entry while ALICE is resident."""
        if os.name != "nt":return
        try:
            import pystray
            from PIL import Image, ImageDraw
            image=Image.new("RGBA",(32,32),(0,0,0,0)); draw=ImageDraw.Draw(image)
            draw.rounded_rectangle((1,5,31,27),radius=11,fill=(5,172,181,255))
            draw.rounded_rectangle((10,10,22,19),radius=2,outline=(235,255,253,255),width=1)
            draw.ellipse((13,13,14,14),fill=(235,255,253,255));draw.ellipse((18,13,19,14),fill=(235,255,253,255))
            draw.line((13,22,19,22),fill=(235,255,253,255),width=1)
            menu=pystray.Menu(
                pystray.MenuItem("Open Mini ALICE",lambda _icon,_item:self._queue_ui("tray_open_mini",self._tray_pointer_position()),default=True),
                pystray.MenuItem("Open full workspace",lambda _icon,_item:self._queue_ui("tray_open_workspace")),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit ALICE",lambda _icon,_item:self._queue_ui("shutdown")),
            )
            self._tray_icon=pystray.Icon("alice-elysium",image,"ALICE is active · click the computer icon for Mini ALICE",menu=menu)
            threading.Thread(target=self._tray_icon.run,daemon=True,name="AliceSystemTray").start()
        except Exception as exc:
            # Tray support must not prevent the assistant from starting.
            self._tray_icon=None
            try:self.runtime.audit.record("tray_icon_unavailable",error=type(exc).__name__)
            except Exception:pass

    def _tray_pointer_position(self):
        """Read the pointer near a tray click without calling Tk from pystray's worker."""
        if os.name != "nt":return None
        try:
            import ctypes
            from ctypes import wintypes
            point=wintypes.POINT()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
                return (int(point.x),int(point.y))
        except Exception:pass
        return None

    def _mini_toggle_text(self):
        """Put keyboard focus in Mini ALICE's always-visible compact composer."""
        try:
            if self._mini_input is not None and self._mini_window is not None and self._mini_window.winfo_exists():
                self._mini_input.focus_set()
        except Exception:pass

    def _mini_stop_voice(self):
        try:self.voice.stop()
        except Exception:pass
        if getattr(self,"jarvis_listener",None) is not None and self.jarvis_listener.running:
            self._stop_jarvis_listener()
        self._publish_orb_state("idle")
        self._set_mini_status("READY")

    def _open_mini_chat(self, anchor=None):
        """Open a compact glass voice-and-text panel from the tray icon."""
        if self._shutdown:return
        self._mini_mode_active=True
        if self._premium_window is not None and self._premium_visible:self.hide_window()
        if self._mini_window is None or not self._mini_window.winfo_exists():
            win=tk.Toplevel(self.root);self._mini_window=win;win.title("Mini ALICE — ALICE Elysium")
            win.overrideredirect(True);win.configure(bg="#09171c")
            try:win.attributes("-topmost",True)
            except tk.TclError:pass
            width,height=560,320;canvas=tk.Canvas(win,width=width,height=height,bg="#09171c",highlightthickness=0)
            canvas.pack(fill="both",expand=True);self._mini_canvas=canvas
            # High-resolution raster surface gives the compact card a smooth, exact radius and edge.
            try:
                from PIL import Image,ImageDraw,ImageFilter,ImageTk
                ratio=3;w,h=width*ratio,height*ratio
                panel=(8*ratio,42*ratio,552*ratio,312*ratio);radius=28*ratio
                shadow=Image.new("RGBA",(w,h),(0,0,0,0));sd=ImageDraw.Draw(shadow)
                sd.rounded_rectangle((panel[0],panel[1]+4*ratio,panel[2],panel[3]+4*ratio),radius=radius,fill=(0,0,0,118))
                shadow=shadow.filter(ImageFilter.GaussianBlur(7*ratio))
                surface=shadow.copy();mask=Image.new("L",(w,h),0);md=ImageDraw.Draw(mask)
                md.rounded_rectangle(panel,radius=radius,fill=255)
                grad=Image.new("RGBA",(w,h),(0,0,0,0));gd=ImageDraw.Draw(grad)
                top=(12,27,35,246);bottom=(12,47,53,246)
                for yy in range(panel[1],panel[3]+1):
                    t=(yy-panel[1])/max(1,panel[3]-panel[1]);color=tuple(round(top[k]*(1-t)+bottom[k]*t) for k in range(4))
                    gd.line((panel[0],yy,panel[2],yy),fill=color,width=1)
                grad.putalpha(mask);surface=Image.alpha_composite(surface,grad)
                outline=ImageDraw.Draw(surface);outline.rounded_rectangle(panel,radius=radius,outline=(78,208,211,242),width=2*ratio)
                inner=(11*ratio,45*ratio,549*ratio,309*ratio)
                outline.rounded_rectangle(inner,radius=25*ratio,outline=(73,145,153,150),width=ratio)
                outline.rounded_rectangle((26*ratio,230*ratio,534*ratio,280*ratio),radius=14*ratio,
                    fill=(8,26,32,248),outline=(51,104,113,235),width=ratio)
                outline.rounded_rectangle((407*ratio,236*ratio,473*ratio,274*ratio),radius=10*ratio,
                    fill=(22,57,64,255),outline=(55,115,123,220),width=ratio)
                outline.rounded_rectangle((480*ratio,236*ratio,528*ratio,274*ratio),radius=10*ratio,
                    fill=(67,201,195,255),outline=(108,226,219,255),width=ratio)
                # Small turquoise computer badge, rendered with the exact same clean antialiasing.
                badge=(254*ratio,4*ratio,306*ratio,35*ratio)
                outline.rounded_rectangle(badge,radius=15*ratio,fill=(7,169,179,255))
                outline.rounded_rectangle((269*ratio,10*ratio,291*ratio,23*ratio),radius=2*ratio,outline=(235,255,253,255),width=2*ratio)
                outline.ellipse((275*ratio,14*ratio,278*ratio,17*ratio),fill=(235,255,253,255))
                outline.ellipse((282*ratio,14*ratio,285*ratio,17*ratio),fill=(235,255,253,255))
                outline.line((275*ratio,20*ratio,285*ratio,20*ratio),fill=(235,255,253,255),width=2*ratio)
                outline.line((276*ratio,25*ratio,284*ratio,25*ratio),fill=(235,255,253,255),width=2*ratio)
                self._mini_surface_image=ImageTk.PhotoImage(surface.resize((width,height),Image.Resampling.LANCZOS))
                canvas.create_image(0,0,anchor="nw",image=self._mini_surface_image)
            except Exception:
                canvas.create_polygon(8,56,8,298,18,312,542,312,552,298,552,56,542,42,18,42,
                    smooth=True,splinesteps=24,fill="#102a30",outline="#4ed0d3",width=1.5)

            # Compact brand/state header.
            canvas.create_oval(28,62,36,70,fill="#66e3c1",outline="")
            canvas.create_text(46,66,anchor="w",text="ALICE",fill="#eaf7f7",font=("Segoe UI",10,"bold"))
            self._mini_status_id=canvas.create_text(95,66,anchor="w",text="READY",fill="#70d9cf",font=("Segoe UI",8,"bold"))
            canvas.create_oval(516,56,537,77,fill="#112a30",outline="#31545b",width=1,tags="mini_close")
            canvas.create_text(526.5,66.5,text="×",fill="#b9d3d5",font=("Segoe UI",11),tags="mini_close")
            canvas.tag_bind("mini_close","<Button-1>",lambda _e:win.withdraw())
            # Mic, dot-matrix activity display and stop control are on one precise line.
            canvas.create_oval(28,88,66,126,fill="#102c32",outline="#44c8ca",width=1,tags="mini_mic")
            canvas.create_oval(42,96,52,110,outline="#8cece7",width=2,tags="mini_mic")
            canvas.create_line(47,110,47,116,fill="#8cece7",width=2,tags="mini_mic")
            canvas.create_arc(39,103,55,120,start=180,extent=180,style="arc",outline="#8cece7",width=2,tags="mini_mic")
            self._mini_dot_ids=[]
            for row_y in (97,107,117):
                for col in range(14):
                    lit=(col+row_y//10)%4!=0
                    self._mini_dot_ids.append(canvas.create_oval(187+col*13,row_y-2.5,192+col*13,row_y+2.5,
                        fill="#58ded9" if lit else "#317a80",outline=""))
            self._mini_stop_id=canvas.create_rectangle(505,95,526,116,fill="#29d1cd",outline="",tags="mini_stop")
            canvas.create_line(27,139,533,139,fill="#31535a",width=1)
            self._mini_response_label=canvas.create_text(29,153,anchor="nw",width=500,text=self._mini_transcript or "Ready when you are.",fill="#e1eded",font=("Segoe UI",14),justify="left")
            canvas.tag_bind("mini_mic","<Button-1>",lambda _e:self._mini_voice_start())
            canvas.tag_bind("mini_stop","<Button-1>",lambda _e:self._mini_stop_voice())
            # Persistent compact chat row with attachment picker and Send.
            canvas.create_line(27,218,533,218,fill="#31535a",width=1)
            self._mini_input=tk.Entry(canvas,bg="#081a20",fg="#e8f3f3",insertbackground="#e8f3f3",
                relief="flat",bd=0,font=("Segoe UI",10))
            self._mini_composer_window=canvas.create_window(39,239,anchor="nw",window=self._mini_input,width=348,height=31)
            self._mini_input.insert(0,"Message ALICE…")
            self._mini_attachment_label=canvas.create_text(29,222,anchor="w",text="",fill="#85d5d0",font=("Segoe UI",8))
            canvas.create_rectangle(407,236,473,274,fill="",outline="",tags="mini_attach")
            canvas.create_rectangle(480,236,528,274,fill="",outline="",tags="mini_send")
            canvas.create_text(440,255,text="＋ Attach",fill="#d3efed",font=("Segoe UI",8),tags="mini_attach")
            canvas.create_text(504,255,text="Send  ➤",fill="#08252a",font=("Segoe UI",8,"bold"),tags="mini_send")
            canvas.tag_bind("mini_attach","<Button-1>",lambda _e:self._mini_attach_files())
            canvas.tag_bind("mini_send","<Button-1>",lambda _e:self._mini_send())
            self._mini_input.bind("<FocusIn>",lambda _e:self._mini_input.delete(0,"end") if self._mini_input.get()=="Message ALICE…" else None)
            self._mini_input.bind("<Return>",lambda _event:(self._mini_send(),"break")[1])
            self._mini_input.bind("<Escape>",lambda _event:(win.withdraw(),"break")[1])
            canvas.bind("<Double-Button-1>",lambda _e:self._mini_toggle_text())
            win.bind("<Escape>",lambda _event:(win.withdraw(),"break")[1])
            win.bind("<Escape>",lambda _event:(win.withdraw(),"break")[1])
            win.protocol("WM_DELETE_WINDOW",win.withdraw)
            self._set_mini_status(self._mini_status)
            try:
                from .win_drop import register_file_drop
                def dropped(paths):self._queue_ui("mini_file_dropped",paths)
                for widget in (win,canvas):
                    hook=register_file_drop(widget.winfo_id(),dropped)
                    if hook:self._mini_drop_hooks.append(hook)
            except Exception:pass
        sw=self.root.winfo_screenwidth();sh=self.root.winfo_screenheight();width,height=560,320
        if anchor and len(anchor)>=2:
            ax,ay=int(anchor[0]),int(anchor[1]);x=ax-width//2;y=ay-height-18 if ay>sh//2 else ay+20
        else:x=(sw-width)//2;y=24
        x=max(0,min(max(0,sw-width),x));y=max(0,min(max(0,sh-height-42),y))
        self._mini_window.geometry(f"{width}x{height}+{x}+{y}")
        self._mini_window.deiconify();self._mini_window.lift();self._mini_window.focus_force()

    def _set_mini_status(self,text):
        self._mini_status=str(text or "READY").upper()
        try:self._mini_canvas.itemconfigure(self._mini_status_id,text=self._mini_status)
        except Exception:pass

    def _mini_refresh_history(self):
        return

    def _mini_attach_files(self):
        if self._mini_window is None:return
        paths=filedialog.askopenfilenames(parent=self._mini_window,title="Attach files to ALICE")
        if not paths:return
        seen={os.path.normcase(str(p)) for p in self._mini_attachments}
        for path in paths:
            resolved=os.path.abspath(path)
            if os.path.isfile(resolved) and os.path.normcase(resolved) not in seen:
                self._mini_attachments.append(resolved); seen.add(os.path.normcase(resolved))
        names=[os.path.basename(p) for p in self._mini_attachments]
        try:self._mini_canvas.itemconfigure(self._mini_attachment_label,text=(f"{len(names)} file(s) attached · "+", ".join(names))[:100] if names else "")
        except Exception:pass

    def _mini_send(self):
        if self._mini_input is None:return
        text=self._mini_input.get().strip()
        if text in {"Ask ALICE anything…","Type a message to ALICE…","Message ALICE…"}:text=""
        if not text and not self._mini_attachments:return
        if self._mini_attachments:
            text=(text+"\n\nUser-selected local attachments (use ALICE's available file tools if the request needs them):\n"+
                  "\n".join("- "+path for path in self._mini_attachments)).strip()
        self._mini_attachments=[]
        try:self._mini_canvas.itemconfigure(self._mini_attachment_label,text="")
        except Exception:pass
        self._mini_input.delete(0,"end")
        self._submit_text(text,source="mini")

    def _open_full_workspace(self):
        if self._mini_window is not None:
            try:self._mini_window.withdraw()
            except tk.TclError:pass
        self._mini_mode_active=False
        self.show_window()

    def _mini_voice_start(self):
        self._open_mini_chat()
        self.root.after(80,self.listen)

    def _set_orb_state(self,state):
        state=str(state or "idle").lower()
        self._orb_state=state if state in {"idle","sleep","awake","listening","thinking","speaking","response"} else "idle"
        labels={"idle":"READY","sleep":"READY","awake":"READY","listening":"LISTENING","thinking":"THINKING","speaking":"SPEAKING","response":"DONE"}
        self._mini_status=labels[self._orb_state]
        if self._mini_window is not None and self._mini_window.winfo_exists():
            self._set_mini_status(self._mini_status)
            self._set_mini_activity(self._orb_state in {"listening","thinking","speaking"})
        try:
            if self._tray_icon is not None:self._tray_icon.title="ALICE is active · "+self._mini_status.replace("·","-")
        except Exception:pass
        try:
            if getattr(self,"_orb_canvas",None) is not None:
                color="#8dc63f" if self._orb_state in {"idle","sleep","awake","response"} else "#c5f18a"
                self._orb_canvas.itemconfigure(self._mini_status_id,text=self._mini_status,fill=color)
                self._orb_canvas.itemconfigure(self._mini_bg,outline=color)
        except Exception:pass
        if self._mini_mode_active and self._orb_state in {"listening","thinking","speaking"}:
            if self._mini_window is None or not self._mini_window.winfo_viewable():self._open_mini_chat()
            self._mini_compact=False
            self._set_mini_status(labels[self._orb_state])
            self._set_mini_activity(True)
            if getattr(self,"_orb_animation_after",None) is None:self._animate_orb_bubble()
        if getattr(self,"_mini_mode_active",False):
            if self._orb_state=="response":
                self._mini_response_pending=True
                self._schedule_mini_compact()
            elif self._orb_state=="speaking":
                self._cancel_mini_compact()
            elif self._orb_state=="idle" and self._mini_response_pending:
                self._mini_response_pending=False
                self._schedule_mini_compact()

    def _set_mini_activity(self,active):
        """Light the reference dot matrix only while ALICE is handling audio/work."""
        if self._mini_window is None or not self._mini_window.winfo_exists():return
        try:
            for index,item in enumerate(self._mini_dot_ids):
                color="#48e5df" if active and index%3 else ("#48d8d5" if index%3 else "#368f91")
                self._mini_canvas.itemconfigure(item,fill=color)
        except Exception:pass

    def _animate_orb_bubble(self):
        if self._shutdown or not self.bubble.winfo_exists():return
        try:
            if self._orb_state not in {"listening","thinking","speaking"}:
                self._orb_animation_after=None
                return
            heights=(7,12,9,15,8)
            for i,item in enumerate(self._mini_wave_ids):
                h=heights[(i+self._orb_phase)%len(heights)] if isinstance(self._orb_phase,int) else heights[(i+int(self._orb_phase))%len(heights)]
                x=251+i*6; self._orb_canvas.coords(item,x,32-h/2,x,32+h/2)
            self._orb_phase=(int(self._orb_phase)+1)%len(heights)
        except Exception as exc:self._log_ui_error(exc)
        finally:
            try:
                if not self._shutdown and self.bubble.winfo_exists() and self._orb_state in {"listening","thinking","speaking"}:self._orb_animation_after=self.root.after(170,self._animate_orb_bubble)
            except tk.TclError:pass

    def _bubble_press(self,event): self._bubble_drag=(event.x_root,event.y_root,self.bubble.winfo_x(),self.bubble.winfo_y(),False)
    def _bubble_drag_move(self,event):
        if not self._bubble_drag:return
        sx,sy,bx,by,moved=self._bubble_drag; dx=event.x_root-sx; dy=event.y_root-sy
        if abs(dx)+abs(dy)>5:moved=True
        width=self._bubble_width if not self._mini_compact else 94; height=self._bubble_height if not self._mini_compact else 34
        x=max(0,min(bx+dx,max(0,self.root.winfo_screenwidth()-width))); y=max(0,min(by+dy,max(0,self.root.winfo_screenheight()-height)))
        self._bubble_drag=(sx,sy,bx,by,moved); self.bubble.geometry(f"{width}x{height}+{x}+{y}")
    def _bubble_release(self,event):
        moved=self._bubble_drag[4] if self._bubble_drag else False; self._bubble_drag=None; self._save_bubble_position()
        if moved:return
        if getattr(self,"_mini_ignore_release",False):self._mini_ignore_release=False;return
        if self._mini_click_after is not None:
            try:self.root.after_cancel(self._mini_click_after)
            except tk.TclError:pass
            self._mini_click_after=None
        self._mini_click_after=self.root.after(230,self._bubble_single_click,event.x)
    def _bubble_single_click(self,x):
        self._mini_click_after=None
        if x>=self._bubble_width-48:self.show_window();return
        self._expand_mini_pill(); self.listen()
    def _bubble_double_click(self,event):
        if self._mini_click_after is not None:
            try:self.root.after_cancel(self._mini_click_after)
            except tk.TclError:pass
            self._mini_click_after=None
        self._mini_ignore_release=True
        self.show_window()
    def _cancel_mini_compact(self):
        if self._mini_compact_after is not None:
            try:self.root.after_cancel(self._mini_compact_after)
            except tk.TclError:pass
            self._mini_compact_after=None
    def _schedule_mini_compact(self):
        self._cancel_mini_compact()
        try:self._mini_compact_after=self.root.after(3000,self._compact_mini_pill)
        except tk.TclError:self._mini_compact_after=None
    def _set_mini_pill_geometry(self):
        if self._mini_window is None or not self._mini_window.winfo_exists():return
        self._set_mini_status(self._mini_status)
    def _expand_mini_pill(self):
        self._mini_compact=False; self._mini_mode_active=True; self._open_mini_chat()
    def _compact_mini_pill(self):
        self._mini_compact_after=None
        if self._mini_mode_active and self._orb_state in {"response","idle"}:
            self._mini_compact=True; self._mini_mode_active=False
            try:self._mini_window.withdraw()
            except Exception:pass
    def _handle_mini_file_drop(self,paths):
        from .win_drop import normalize_dropped_paths
        safe=normalize_dropped_paths(paths)
        if not safe:return
        self._mini_mode_active=False; self.show_window()
        self._publish_premium_event("file_dropped",{"paths":safe})
        self._set_orb_state("awake")
        self.say("Alice",f"I received {len(safe)} dropped file{'s' if len(safe)!=1 else ''} and opened the workspace. I haven't opened, read, or changed them.")
    def _show_bubble_menu(self,event):
        try:self._update_menu_labels(); self._bubble_menu.tk_popup(event.x_root,event.y_root)
        finally:
            try:self._bubble_menu.grab_release()
            except Exception:pass
    def _restore_bubble_position(self):
        width=getattr(self,"_bubble_width",getattr(self,"_bubble_size",72)); height=getattr(self,"_bubble_height",width); x=max(8,(self.root.winfo_screenwidth()-width)//2); y=12
        try:data=json.loads(self._bubble_state_path.read_text(encoding="utf-8")) if self._bubble_state_path.exists() else {}; x=int(data.get("x",x)); y=int(data.get("y",y))
        except Exception:pass
        sw=max(1,self.root.winfo_screenwidth()); sh=max(1,self.root.winfo_screenheight()); x=max(0,min(x,sw-width)); y=max(0,min(y,sh-height)); self.bubble.geometry(f"{width}x{height}+{x}+{y}")
    def _save_bubble_position(self):
        try:self._bubble_state_path.parent.mkdir(parents=True,exist_ok=True); self._bubble_state_path.write_text(json.dumps({"x":self.bubble.winfo_x(),"y":self.bubble.winfo_y()},indent=2),encoding="utf-8")
        except Exception:pass

    def _refocus_entry(self):
        if self._shutdown: return
        try:
            # Never resurrect a deliberately hidden/iconified ALICE window when
            # a background response finishes. This preserves Windows snap/split
            # layouts and lets the user keep other apps in focus.
            if self.root.state()=="iconic": return
            self.entry.focus_set()
        except Exception:
            pass

    def _restore_window_state(self):
        try:
            if self._window_state_path.exists():
                data=json.loads(self._window_state_path.read_text(encoding="utf-8")); geometry=str(data.get("geometry","")).strip(); self._saved_window_state=str(data.get("state","normal")); self._window_fullscreen=bool(data.get("fullscreen",False))
                if geometry:self.root.geometry(geometry)
                if self._window_fullscreen:self.root.attributes("-fullscreen",True)
                elif self._saved_window_state=="zoomed":self.root.state("zoomed")
        except Exception:pass
    def _schedule_window_state_save(self):
        if self._shutdown:return
        try:
            if self._window_save_after is not None:self.root.after_cancel(self._window_save_after)
        except Exception:pass
        try:self._window_save_after=self.root.after(500,self._save_window_state)
        except Exception:pass
    def _save_window_state(self):
        try:self._window_state_path.parent.mkdir(parents=True,exist_ok=True); self._window_state_path.write_text(json.dumps({"geometry":self.root.geometry(),"state":self.root.state(),"fullscreen":self._window_fullscreen},indent=2),encoding="utf-8")
        except Exception:pass
    def toggle_maximize(self):
        if self._window_fullscreen:self.toggle_fullscreen(); return
        try:self.root.state("normal" if self.root.state()=="zoomed" else "zoomed")
        except Exception:pass
        self._schedule_window_state_save()
    def toggle_fullscreen(self):
        self._window_fullscreen=not self._window_fullscreen
        try:self.root.attributes("-fullscreen",self._window_fullscreen)
        except Exception:pass
        self._schedule_window_state_save()
    def show_window(self):
        if self._shutdown:return
        if self._premium_window is not None:
            try:
                self._premium_visible=True; self._mini_mode_active=False; self.bubble.withdraw(); self._premium_window.show(); return
            except Exception:pass
        try:
            # Iconify/deiconify preserves Windows snap/split placement more reliably than withdraw/deiconify.
            self.bubble.withdraw(); self.root.deiconify(); self.root.update_idletasks()
            if self._window_fullscreen:self.root.attributes("-fullscreen",True)
            elif self._saved_window_state=="zoomed":self.root.state("zoomed")
            self.root.lift(); self.entry.focus_set()
        except Exception:pass
    def hide_window(self):
        if not self._shutdown:
            if self._premium_window is not None:
                try:self._premium_visible=False; self._premium_window.hide(); return
                except Exception:pass
            try:self._saved_window_state=self.root.state()
            except Exception:self._saved_window_state="normal"
            self._save_window_state(); self.root.iconify()
    def toggle_window(self):
        if self._shutdown:return
        if self._premium_window is not None:
            self.hide_window() if self._premium_visible else self.show_window()
            self._premium_visible=not self._premium_visible
            return
        try:state=self.root.state()
        except Exception:state="normal"
        if state=="iconic":self.show_window()
        else:self.hide_window()

    def shutdown(self):
        if self._shutdown:return
        self._shutdown=True
        if self._cancel_event is not None:self._cancel_event.set()
        try:
            if self.remote_mobile_service is not None:self.remote_mobile_service.shutdown()
        except Exception:pass
        try:self.jarvis_listener.stop(timeout=0.2)
        except Exception:pass
        try:self.voice.stop()
        except Exception:pass
        try:self.hotkey.stop()
        except Exception:pass
        try:
            if self._tray_icon is not None:self._tray_icon.stop()
        except Exception:pass
        try:self.runtime.stop_scheduler()
        except Exception:pass
        try:self._save_window_state()
        except Exception:pass
        try:self._save_bubble_position()
        except Exception:pass
        try:
            if self._hud_chatbox is not None:self._hud_chatbox.close()
        except Exception:pass
        try:self.bubble.destroy()
        except Exception:pass
        try:
            if self._mini_window is not None and self._mini_window.winfo_exists():self._mini_window.destroy()
        except Exception:pass
        try:self._native_accessible_entry.close()
        except Exception:pass
        self.root.destroy()

    @property
    def root_path(self):
        from pathlib import Path
        configured=os.getenv("ALICE_DATA_ROOT","").strip()
        if configured:
            return Path(configured).expanduser().resolve()
        return Path(__file__).resolve().parents[2]

    def _restore_conversation(self):
        rows=self.conversation.recent(80)
        if not rows:
            return
        self.chat.config(state="normal")
        self.chat.insert("end", "--- Restored conversation history ---\n")
        for row in rows:
            role=str(row.get("role",""))
            label="You" if role=="user" else "Alice" if role=="assistant" else role.title()
            self.chat.insert("end", f"{label}: {row.get("content","")}\n\n")
        self.chat.config(state="disabled")
        self.chat.see("end")

    def _history_prompt(self):
        return self.conversation.prompt_context(limit=14, max_chars=10000)

    def provider_status(self):
        mode=getattr(getattr(self.router,"runtime_policy",None),"mode","gemini_primary")
        if mode=="gemini_primary":
            if not os.getenv("GEMINI_API_KEY","").strip():
                return "Brain: Gemini primary • setup required"
            return "Brain: Gemini primary • configured (connection not tested)"
        if mode=="local_required":
            return "Brain: Local-only (AI API keys blocked)"
        active=", ".join(k for k,v in self.router.available().items() if v)
        if not active:return f"Brain: {mode} • no AI providers configured"
        return f"Brain: {mode} • configured (not connection-tested): "+active

    def provider_setup(self):
        """Configure Gemini locally and provide an explicit connection test."""
        win=tk.Toplevel(self.root); win.title("ALICE Brain Setup"); win.geometry("620x760"); win.transient(self.root); win.grab_set()
        tk.Label(win,text="ALICE Brain · Gemini primary",font=("Segoe UI",16,"bold")).pack(pady=(18,8))
        tk.Label(win,text="Gemini handles chat, planning, and task interpretation. ALICE validates every proposed tool through its existing permission and confirmation gates. The API key stays in this PC's .env file and is never shown here.",wraplength=560,justify="left").pack(padx=25,pady=6,anchor="w")
        tk.Label(win,text="Gemini API key (leave blank to keep the saved key)",anchor="w").pack(fill="x",padx=25,pady=(10,2))
        key_entry=ttk.Entry(win,show="•",width=64)
        key_entry.pack(fill="x",padx=25)
        tk.Label(win,text="Use a Free Tier AI Studio project key if you want to avoid paid usage. ALICE does not enable billing; verify the project's tier and quotas in AI Studio.",wraplength=560,justify="left").pack(padx=25,pady=6,anchor="w")
        tk.Label(win,text="Model ID",anchor="w").pack(fill="x",padx=25,pady=(6,2))
        model_entry=ttk.Entry(win,width=44)
        model_entry.insert(0,str(getattr(self.router,"gemini_model","gemini-3.8-flash")))
        model_entry.pack(anchor="w",padx=25)
        gemini_state=tk.StringVar(value=("Key configured; connection not tested" if self.router.available().get("gemini") else "No Gemini key configured"))
        tk.Label(win,textvariable=gemini_state,anchor="w",fg="#155e53").pack(fill="x",padx=25,pady=8)
        def save_gemini():
            from ..providers.configuration import save_gemini_config, save_gemini_model
            token=key_entry.get().strip()
            if not token and not os.getenv("GEMINI_API_KEY","").strip():
                messagebox.showerror("Gemini setup incomplete","Enter the Gemini API key in this window. Do not paste it into chat.",parent=win)
                return
            try:
                if token:
                    save_gemini_config(self.root_path/".env",token,model_entry.get())
                else:
                    save_gemini_model(self.root_path/".env",model_entry.get())
                self.router.reload_config()
                key_entry.delete(0,"end")
                gemini_state.set("Saved locally · connection not tested")
                self.activity.config(text=self.provider_status())
                messagebox.showinfo("Gemini settings saved","Gemini is selected as ALICE's primary brain. No connection request was sent yet.",parent=win)
            except Exception as exc:
                messagebox.showerror("Gemini settings not saved",str(exc),parent=win)
        def test_gemini():
            if not self.router.available().get("gemini"):
                gemini_state.set("Save a Gemini key before testing")
                return
            gemini_state.set("Testing one short Gemini request…")
            selected_model=model_entry.get().strip()
            def run_test():
                try:
                    result=self.router.test_gemini_connection(model=selected_model)
                    message=f"PASS · Gemini {result['model']} responded in {result['elapsed_seconds']}s"
                    win.after(0,lambda: (gemini_state.set(message),messagebox.showinfo("Gemini connection test",message,parent=win)))
                except Exception as exc:
                    message=str(exc)
                    win.after(0,lambda: (gemini_state.set("Connection test failed · see message"),messagebox.showerror("Gemini connection test failed",message,parent=win)))
            threading.Thread(target=run_test,name="alice-gemini-connection-test",daemon=True).start()
        buttons=ttk.Frame(win); buttons.pack(fill="x",padx=25,pady=4)
        ttk.Button(buttons,text="Save Gemini settings",command=save_gemini).pack(side="left")
        ttk.Button(buttons,text="Test connection",command=test_gemini).pack(side="left",padx=8)
        ttk.Separator(win).pack(fill="x",padx=25,pady=12)
        tk.Label(win,text="Optional local quick-chat fallback settings",font=("Segoe UI",11,"bold")).pack(anchor="w",padx=25,pady=(4,2))
        tk.Label(win,text="The local model is not contacted automatically while Gemini is primary. Choose Local-only in the environment settings if you want an offline-only mode.",wraplength=560,justify="left").pack(anchor="w",padx=25,pady=(0,6))
        status=self.router.local_status()
        state="Ready" if status.get("model_available") else "Not ready — local service or configured model is unavailable"
        fast_model=os.getenv("ALICE_LOCAL_FAST_MODEL",self.router.local_fast_model)
        fast_available=fast_model in status.get("models",[])
        details=f"Status: {state}\nPrimary model: {status.get('model','unknown')}\nQuick chat model: {fast_model} ({'installed' if fast_available else 'not installed; primary model will be used'})\nOllama reachable: {'yes' if status.get('reachable') else 'no'}\nPrimary model installed: {'yes' if status.get('model_available') else 'no'}\nModel keep-alive: {os.getenv('ALICE_LOCAL_MODEL_KEEP_ALIVE','20m')}"
        details_label=tk.Label(win,text=details,justify="left",anchor="w",font=("Consolas",10))
        details_label.pack(fill="x",padx=25,pady=12)
        tk.Label(win,text="Quick chat speed",font=("Segoe UI",11,"bold")).pack(anchor="w",padx=25,pady=(4,2))
        tk.Label(win,text="Used only for short, simple chat. Planning, research, and actions keep the primary model.",wraplength=500,justify="left").pack(anchor="w",padx=25,pady=(0,6))
        installed=set(status.get("models",[]))
        fast_choices=[name for name in ("gemma3:270m","gemma3:1b") if name in installed]
        if fast_model in installed and fast_model not in fast_choices:
            fast_choices.append(fast_model)
        fast_choice=tk.StringVar(value=fast_model if fast_model in fast_choices else (fast_choices[0] if fast_choices else ""))
        selector=ttk.Combobox(win,textvariable=fast_choice,values=fast_choices,state="readonly" if fast_choices else "disabled",width=30)
        selector.pack(anchor="w",padx=25,pady=4)
        tk.Label(win,text="gemma3:270m is fastest; gemma3:1b is a slower, more capable quick-chat choice.",wraplength=500,justify="left").pack(anchor="w",padx=25,pady=(0,6))
        def save_fast_chat_model():
            from ..providers.configuration import save_local_fast_model
            try:
                save_local_fast_model(self.root_path/".env",fast_choice.get(),status.get("models",[]))
            except Exception as exc:
                messagebox.showerror("Quick chat model not saved",str(exc),parent=win)
                return
            self.router.local_fast_model=fast_choice.get()
            details_label.configure(text=details.replace(f"Quick chat model: {fast_model}",f"Quick chat model: {fast_choice.get()} (installed)"))
            messagebox.showinfo("Brain speed updated","Quick chat will use the selected model immediately. Longer reasoning, research, and actions still use the primary model.",parent=win)
        tk.Button(win,text="Save quick chat model",command=save_fast_chat_model,width=22,state="normal" if fast_choices else "disabled").pack(anchor="w",padx=25,pady=(2,8))
        tk.Label(win,text="Ollama is an optional local provider for offline use. Internet research uses ALICE's existing source tools; the Gemini reasoning model does not automatically ground answers in web search. Fish Audio speech remains separate from Gemini.",wraplength=560,justify="left").pack(padx=25,pady=6,anchor="w")
        tk.Button(win,text="Close",command=win.destroy,width=12).pack(pady=18)

    def build_tools(self):
        from ..execution.postconditions import PostconditionRegistry
        from ..browser.postconditions import (verify_browser_open_postcondition,
            verify_browser_new_tab_postcondition,verify_browser_switch_tab_postcondition,
            verify_browser_fill_postcondition, verify_browser_recover_postcondition)
        from ..builder.postconditions import verify_builder_project_postcondition
        from ..builder.isolation import DockerBuilderTestRunner
        from ..computer.postconditions import verify_open_app_postcondition
        from ..computer.postconditions import verify_accessible_click_postcondition
        from ..computer.verified_click import click_with_expected_text, verify_verified_desktop_click
        from ..computer.verified_scroll import scroll_with_expected_text, verify_verified_desktop_scroll
        from ..computer.verified_keyboard import (tab_to_next_focus, verify_focus_navigation,
            press_key_with_expected_text, verify_verified_desktop_keypress)
        from ..computer.verified_typing import type_into_empty_focused_control, verify_desktop_typing
        from ..computer.verified_drag import drag_accessible_element, verify_accessible_drag_postcondition
        from ..computer.verified_mouse import move_pointer_to_verified, verify_pointer_position_postcondition
        from ..computer.uia import WindowsUIAutomation
        from ..messaging.whatsapp import verify_whatsapp_send_postcondition
        from ..workspace.postconditions import verify_workspace_file_write_postcondition
        from ..weather import OpenMeteoWeather, verify_weather_lookup_postcondition
        from ..computer.system_tools import (WindowsHardware, verify_brightness_change_postcondition,
            verify_volume_change_postcondition)
        from ..multimodal.camera import CameraCapture, verify_camera_capture_postcondition
        from ..multimodal.analyzer import MultimodalAnalyzer
        from ..integrations.public_ip import PublicIPLookup, verify_public_ip_postcondition
        from ..weather import OpenMeteoWeather, verify_weather_lookup_postcondition
        from ..computer.system_tools import WindowsHardware
        from ..multimodal.camera import CameraCapture, verify_camera_capture_postcondition
        from ..multimodal.analyzer import MultimodalAnalyzer
        from ..execution.postconditions import PostconditionResult
        from ..devices.graph import DeviceGraph
        from ..devices.registry import DeviceRegistry
        from ..android_intelligence.postconditions import (verify_android_launch_postcondition,
            verify_android_text_postcondition,type_android_text_with_baseline,
            tap_android_element_with_expected_transition,verify_android_tap_postcondition,
            press_android_key_with_expected_transition,swipe_android_with_expected_transition)
        t=ToolRegistry(capability_manager=self.capabilities); terminal=WindowsTerminal(); pc=ComputerController(); discovery=self.app_discovery; grounder=ScreenGrounder(); sm=SelfManager(router=self.router); gluttony=self.gluttony; mobile=AndroidController(); browser=BrowserAgent(); researcher=self.web_research; builder=BuilderEngine(self.router,researcher=researcher,test_runner=DockerBuilderTestRunner())
        hardware=WindowsHardware(); weather=OpenMeteoWeather(); camera=CameraCapture(self.root_path); media=MultimodalAnalyzer(router=self.router); public_ip=PublicIPLookup()
        hardware=WindowsHardware(); weather=OpenMeteoWeather(); camera=CameraCapture(self.root_path); media=MultimodalAnalyzer(router=self.router)
        t.postconditions=PostconditionRegistry()
        gmail_credentials = GmailCredentialStore(
            self.root_path / "alice_workspace" / "runtime" / "credentials" / "gmail_oauth.dpapi")
        gmail_provider = GmailReadOnlyProvider(gmail_credentials)
        email_tools = register_email_tools(t, self.root_path, provider=gmail_provider)
        self.email_service = email_tools["service"]
        self.trading_lab = register_trading_tools(t, self.root_path, researcher)
        self.trading_lab.chart_analyzer = media.analyze_screen
        t.postconditions.register("build_project",lambda args,result:verify_builder_project_postcondition(args,result,builder.projects,"alice-project"))
        t.postconditions.register("build_ai_agent",lambda args,result:verify_builder_project_postcondition(args,result,builder.projects,"alice-agent"))
        t.postconditions.register("open_app",lambda args,result:verify_open_app_postcondition(discovery,args,result))
        t.postconditions.register("acquire_knowledge",self.knowledge_acquirer.verify_acquisition_postcondition)
        t.postconditions.register("desktop_click_accessible",lambda args,result:
            verify_accessible_click_postcondition(WindowsUIAutomation(),args,result))
        t.postconditions.register("desktop_click_verified",lambda args,result:
            verify_verified_desktop_click(WindowsUIAutomation(),args,result))
        t.postconditions.register("desktop_scroll_verified",lambda args,result:
            verify_verified_desktop_scroll(WindowsUIAutomation(),args,result))
        t.postconditions.register("desktop_focus_navigate",lambda args,result:
            verify_focus_navigation(WindowsUIAutomation(),args,result))
        t.postconditions.register("desktop_press_verified",lambda args,result:
            verify_verified_desktop_keypress(WindowsUIAutomation(),args,result))
        t.postconditions.register("desktop_type_verified",lambda args,result:
            verify_desktop_typing(WindowsUIAutomation(),args,result))
        t.postconditions.register("desktop_drag_accessible",lambda args,result:
            verify_accessible_drag_postcondition(WindowsUIAutomation(),args,result))
        t.postconditions.register("desktop_move_verified",lambda args,result:
            verify_pointer_position_postcondition(pc,args,result))
        device_graph=DeviceGraph(self.root_path,DeviceRegistry(self.root_path))
        from ..android.adb import ADBAdapter
        from ..android_intelligence import AndroidIntelligenceController
        from ..messaging.whatsapp import AndroidWhatsAppUIObserver, VisibleChatDeliveryVerifier, VerifiedWhatsAppComposer
        from ..messaging.whatsapp_interface import WhatsAppInterface, android_text_command
        from ..security.device_consent import DeviceConsent
        wa_adb=ADBAdapter(); android_observer=AndroidIntelligenceController()
        wa_observer=AndroidWhatsAppUIObserver(android_observer)
        wa_verifier=VisibleChatDeliveryVerifier(wa_observer); wa_consent=DeviceConsent(self.root_path)
        class WhatsAppAndroidControl:
            adb=wa_adb
            def _target(self, device_id):
                serial=str(device_id)
                if serial not in self.adb.devices():
                    raise ConnectionError("Android device is not connected through authorized ADB")
                return serial
            def prepare_message(self, device_id, chat, value):
                self._target(device_id)
                return wa_composer.prepare(device_id,chat,value)
            def text(self, value, serial):
                self.adb.shell(self._target(serial),android_text_command(value))
                return {"ok":True}
        wa_control=WhatsAppAndroidControl()
        wa_composer=VerifiedWhatsAppComposer(wa_control,android_observer,wa_observer)
        whatsapp=WhatsAppInterface(wa_control, None, wa_consent, wa_verifier)
        def whatsapp_visible_chat(device_id, chat):
            view=wa_observer.read_visible_chat(device_id, chat)
            return {"ok":True,"chat":view["chat"],"visible_outgoing_count":len(view["messages"]),
                    "evidence_ids":[row["id"] for row in view["messages"]]}
        def whatsapp_send_reply(device_id, chat, text):
            return whatsapp.send_reply(device_id, text, chat=chat)
        def android_launch_app(serial, package):
            if not serial:
                raise ValueError("An explicit authorized Android serial is required for launch verification")
            return mobile.launch_package(package, serial)
        def android_text(serial, text):
            return type_android_text_with_baseline(mobile, android_observer, serial, text)
        def android_tap(serial, target_text, expected_text=None, expected_package=None):
            return tap_android_element_with_expected_transition(
                android_observer, android_observer, serial, target_text,
                expected_text=expected_text, expected_package=expected_package)
        def android_keyevent(serial, key, expected_text=None, expected_package=None):
            return press_android_key_with_expected_transition(
                android_observer, android_observer, serial, key,
                expected_text=expected_text, expected_package=expected_package)
        def android_swipe(serial, x1, y1, x2, y2, duration_ms=400, expected_text=None, expected_package=None):
            return swipe_android_with_expected_transition(
                android_observer, android_observer, serial, x1, y1, x2, y2, duration_ms,
                expected_text=expected_text, expected_package=expected_package)
        def device_graph_snapshot(source_id=None, target_id=None):
            if (source_id is None) != (target_id is None):
                raise ValueError("Provide both source_id and target_id to request an advisory route")
            return device_graph.route(source_id, target_id) if source_id is not None else device_graph.snapshot()
        def device_graph_link(source_id, target_id, relation):
            return device_graph.link(source_id, target_id, relation)
        def analyze_camera_image(path, prompt="Describe the captured scene", confirm_image_processing=False):
            if confirm_image_processing is not True:
                raise PermissionError("Camera images need explicit confirmation before model analysis.")
            from pathlib import Path
            capture_root=(self.root_path/"alice_workspace"/"captures"/"camera").resolve()
            image=Path(str(path)).expanduser().resolve()
            try:image.relative_to(capture_root)
            except ValueError as exc:raise PermissionError("Analyze only images captured by ALICE's camera tool.") from exc
            observation=media.analyze_camera_frame(str(image),str(prompt)[:1000])
            return {"ok":True,"observation":observation.to_dict(),"reliability":getattr(observation,"reliability",{})}
        def analyze_camera_image(path, prompt="Describe the captured scene", confirm_image_processing=False):
            if confirm_image_processing is not True:
                raise PermissionError("Camera images need explicit confirmation before model analysis.")
            from pathlib import Path
            capture_root=(self.root_path/"alice_workspace"/"captures"/"camera").resolve()
            image=Path(str(path)).expanduser().resolve()
            try:image.relative_to(capture_root)
            except ValueError as exc:raise PermissionError("Analyze only images captured by ALICE's camera tool.") from exc
            observation=media.analyze_camera_frame(str(image),str(prompt)[:1000])
            return {"ok":True,"observation":observation.to_dict(),"reliability":getattr(observation,"reliability",{})}
        def verify_brightness_change(args,result):
            current=hardware.brightness_status(); levels=current.get("levels",[]) if current.get("ok") else []
            try:expected=hardware._percentage(args.get("percent"))
            except Exception:expected=None
            observed=bool(levels) and expected is not None and all(int(value)==expected for value in levels)
            ok=observed and isinstance(result,dict) and result.get("ok") is True and result.get("verified") is True
            return PostconditionResult(ok,{"observed":bool(observed),"levels":levels,"requested":expected},
                                       "fresh WMI brightness readback" if ok else "brightness_readback_mismatch")
        def verify_volume_change(args,result):
            current=hardware.volume_status(); observed=current.get("percent") if current.get("ok") else None
            try:expected=hardware._percentage(args.get("percent"))
            except Exception:expected=None
            matched=observed is not None and expected is not None and abs(int(observed)-expected)<=1
            ok=matched and isinstance(result,dict) and result.get("ok") is True and result.get("verified") is True
            return PostconditionResult(ok,{"observed":bool(matched),"percent":observed,"requested":expected},
                                       "fresh Windows volume readback" if ok else "volume_readback_mismatch")
        t.postconditions.register(
            "whatsapp_send_reply",
            lambda args, result: verify_whatsapp_send_postcondition(wa_verifier, args, result),
        )
        t.postconditions.register("write_file", verify_workspace_file_write_postcondition)
        t.postconditions.register("weather_lookup",verify_weather_lookup_postcondition)
        t.postconditions.register("public_ip_lookup",verify_public_ip_postcondition)
        t.postconditions.register("set_display_brightness",lambda args,result:verify_brightness_change_postcondition(args,result,hardware))
        t.postconditions.register("set_system_volume",lambda args,result:verify_volume_change_postcondition(args,result,hardware))
        t.postconditions.register("capture_camera_image",lambda args,result:verify_camera_capture_postcondition(args,result,self.root_path))
        t.postconditions.register("device_graph_link", device_graph.verify_link_postcondition)
        t.postconditions.register("devour_repository",self.devour.verify_single_postcondition)
        t.postconditions.register("devour_multiple_repositories", self.devour.verify_multi_postcondition)
        t.postconditions.register("devour_objective",self.devour.verify_objective_postcondition)
        t.postconditions.register("browser_open",lambda args,result:verify_browser_open_postcondition(browser,args,result))
        t.postconditions.register("browser_new_tab",lambda args,result:verify_browser_new_tab_postcondition(browser,args,result))
        t.postconditions.register("browser_switch_tab",lambda args,result:verify_browser_switch_tab_postcondition(browser,args,result))
        t.postconditions.register("browser_fill",lambda args,result:verify_browser_fill_postcondition(browser,args,result))
        t.postconditions.register("browser_recover",lambda args,result:verify_browser_recover_postcondition(browser,args,result))
        t.postconditions.register("android_launch_app",lambda args,result:verify_android_launch_postcondition(android_observer,args,result))
        t.postconditions.register("android_text",lambda args,result:verify_android_text_postcondition(android_observer,args,result))
        t.postconditions.register("android_tap",lambda args,result:verify_android_tap_postcondition(android_observer,args,result))
        t.postconditions.register("android_swipe",lambda args,result:verify_android_tap_postcondition(android_observer,args,result))
        t.postconditions.register("android_keyevent",lambda args,result:verify_android_tap_postcondition(android_observer,args,result))
        creator=CreationService(router=self.router, builder=builder, image_provider=OpenAIImageProvider(), root=self.root_path)
        def generate_image(prompt, filename="image.png", size="1024x1024"):
            request=CreationRequest(prompt=str(prompt), kind=ArtifactKind.IMAGE, filename=str(filename), context={"size":str(size)})
            artifact=creator.create(request)
            if not artifact.exists:
                raise RuntimeError("Image provider returned without creating a verifiable artifact")
            return {"ok":True,"path":artifact.path,"kind":artifact.kind.value,"description":artifact.description,"metadata":artifact.metadata}
        deps=DependencyManager(permission=terminal.run); forge=SkillForge(self.router,capabilities=self.capabilities)
        acquirer=CapabilityAcquirer(self.router,self.capabilities,researcher=researcher)
        def acquire_capability(goal, capability='', allow_research=True):
            result=acquirer.acquire(goal, capability, allow_research)
            if result.get('ok') and result.get('status') == 'acquired':
                import importlib.util
                skill=result.get('skill', {}); name=skill.get('name'); path=skill.get('path')
                if name and path:
                    spec=importlib.util.spec_from_file_location(name,path); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
                    if not hasattr(mod,'run'): raise RuntimeError('Acquired capability has no run(**kwargs)')
                    t.add(name,skill.get('description','Learned capability'),mod.run,'execute'); result['activated_tool']=name
            return result
        def learn_skill(goal, missing_capability=''):
            result=forge.learn(goal,missing_capability)
            import importlib.util
            spec=importlib.util.spec_from_file_location(result['name'],result['path']); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
            if not hasattr(mod,'run'): raise RuntimeError('Generated skill has no run(**kwargs)')
            t.add(result['name'],result['description'],mod.run,'execute'); return result
        def delegate_specialist(prompt,providers=None): return self.router.specialist(prompt,providers=providers)
        def multi_agent_task(objective, roles=None, context="", verify=True):
            role_names = roles or ["researcher", "ui_analyst"]; specs=[]
            presets={"researcher":["fetch_webpage","browser_page_text","browser_snapshot","list_files","read_file","capability_inventory"],"ui_analyst":["take_screenshot","ground_screen","screen_state","running_apps","browser_snapshot"],"tester":["list_files","read_file","run_windows_command"],"documenter":["list_files","read_file","write_file"],"coder":["list_files","read_file","write_file","build_project"]}
            risk={"researcher":"read","ui_analyst":"read","tester":"read","documenter":"write","coder":"write"}
            for i, role in enumerate(role_names):
                if role not in presets: raise ValueError("Unknown worker role: "+str(role))
                specs.append(WorkerSpec(f"{role}-{i+1}",role,objective,[n for n in presets[role] if n in t.tools],risk=risk[role]))
            return self.multi_agent.run(objective,specs=specs,context=context,verify=verify)
        t.add("list_files","List files in Alice workspace",list_files,"read"); t.add("read_file","Read a workspace file",read_file,"read"); t.add("write_file","Write a workspace file",write_file,"write")
        t.add("assimilate_repository","Safely ingest a public GitHub repository into quarantine, scan it, decompose its architecture, and build an ALICE capability report without executing imported code",gluttony.assimilate,"write"); t.add("devour_repository","Devour a public GitHub URL, source file, supported archive, or local project folder into quarantine and produce a native reimplementation plan without executing external code",self.devour.devour,"write")
        t.add("devour_multiple_repositories","Analyze 2 to 8 local projects or public GitHub repositories in one governed quarantine job, compare license/security and capability evidence, and record a deterministic combined digest without executing, promoting, or upgrading imported code",self.devour.devour_many,"write")
        t.add("devour_discover","Search public GitHub repositories for a described ALICE capability and compare candidates without downloading or executing them",self.devour.discover_candidates,"external")
        t.add("devour_objective","Discover and rank public GitHub repositories for a capability objective, automatically select the top candidates, quarantine and statically compare them, and leave each capability unapproved with no imported-code execution or promotion",self.devour.devour_objective,"external")
        t.add("devour_report","Read the latest Devour v2 capability comparison report without executing external code",self.devour.latest_report,"read")
        t.add("devour_inspect_installer","Read-only inspect a Windows EXE or MSI installer: hash it, read PE headers, and check Authenticode when Windows PowerShell is available. Never runs or installs the file; this is metadata only.",self.devour.inspect_installer,"write")
        t.add("gluttony_inventory","Show repositories ALICE has analyzed and the safe capabilities identified",gluttony.inventory,"read")
        t.add("alice_source_inventory","Inspect ALICE's own non-protected source inventory",sm.source_inventory,"read")
        t.add("alice_read_source","Read a non-protected ALICE source file for self-inspection",sm.read_source,"read")
        t.add("alice_workspace_status","Inspect safe metadata about ALICE's persistent workspace",sm.workspace_status,"read")
        def local_ai_status():
            status=self.router.local_status()
            status["ok"]=True
            status["api_key_required"]=False
            strict=getattr(getattr(self.router,"runtime_policy",None),"mode","local_required")=="local_required"
            status["brain_mode"]="local_required" if strict else getattr(self.router.runtime_policy,"mode","auto")
            status["message"]=("Local-only brain is ready. AI reasoning uses the installed local model; hosted AI APIs are blocked."
                                if status.get("model_available") and strict else
                                "Local model is available, but hosted providers are allowed by the selected brain mode."
                                if status.get("model_available") else
                                "Local model is not ready. Start Ollama and install the configured model; in local-only mode ALICE will not fall back to an API key.")
            return status
        t.add("local_ai_status","Check API-key-free local model and self-engineering readiness",local_ai_status,"read")
        def self_engineering_status():
            s=self.router.local_status()
            strict=getattr(getattr(self.router,"runtime_policy",None),"mode","local_required")=="local_required"
            return {"brain_mode":getattr(self.router.runtime_policy,"mode","auto"),
                "local_first":True if strict else os.getenv("ALICE_SELF_ENGINEER_LOCAL_FIRST","1"),
                "require_local":True if strict else os.getenv("ALICE_SELF_ENGINEER_REQUIRE_LOCAL","0"),
                "allow_remote_fallback":False if strict else os.getenv("ALICE_SELF_ENGINEER_ALLOW_REMOTE_FALLBACK","1"),
                "local":s,"voice":self.voice.voice_contract() if hasattr(self,"voice") else {}}
        t.add("self_engineering_status","Show local-engineering policy, model readiness and voice persistence contract",self_engineering_status,"read")
        t.add("desktop_observe_actions","List up to 100 enabled visible button/link names in the foreground Windows window, excluding editable text contents",WindowsUIAutomation().visible_actions,"read")
        t.add("desktop_click_accessible","Click one unique foreground Windows UI Automation button or link by exact accessible name and require new visible expected_text",WindowsUIAutomation(pc).click_exact,"execute")
        t.add("desktop_click_verified","Click one in-bounds desktop coordinate only when expected_text is absent, then require fresh UI Automation readback of that new text",lambda x,y,expected_text:click_with_expected_text(pc,WindowsUIAutomation(),x,y,expected_text),"execute")
        t.add("desktop_scroll_verified","Scroll 1-20 notches only when expected_text is absent, then require fresh UI Automation readback of that new text",lambda amount,expected_text:scroll_with_expected_text(pc,WindowsUIAutomation(),amount,expected_text),"execute")
        t.add("desktop_focused_control","Read safe metadata for the currently focused foreground control without returning editable field contents",WindowsUIAutomation().focused_control,"read")
        t.add("desktop_type_verified","Type printable ASCII into one focused, empty, non-password edit control and verify the exact value by hash/length readback",lambda text:type_into_empty_focused_control(pc,WindowsUIAutomation(),text),"execute")
        t.add("desktop_drag_accessible","Drag one uniquely named accessible item into one uniquely named list, tree, or grid and verify fresh UI Automation state",lambda source_name,target_name,source_role="list_item",target_role="list":drag_accessible_element(pc,WindowsUIAutomation(),source_name,target_name,source_role,target_role),"execute")
        t.add("desktop_move_verified","Move pointer to an in-bounds desktop coordinate and independently verify pointer position",lambda x,y:move_pointer_to_verified(pc,x,y),"execute")
        t.add("desktop_focus_navigate","Move focus one step forward with Tab or backward with Shift+Tab, and verify a fresh UI Automation focus transition",lambda direction="forward":tab_to_next_focus(pc,WindowsUIAutomation(),direction),"execute")
        t.add("desktop_press_verified","Press Enter, Escape, Space, an arrow, Home, End, PageUp or PageDown only when expected_text is absent, then verify it in a fresh foreground UI Automation read",lambda key,expected_text:press_key_with_expected_text(pc,WindowsUIAutomation(),key,expected_text),"execute")
        t.add("open_app","Open a normal Windows application by name/path",open_app,"execute"); t.add("open_url","Open HTTP/HTTPS URL in default browser",open_url,"external"); t.add("fetch_webpage","Fetch webpage text",fetch,"external"); t.add("acquire_knowledge","Research public/authorized sources, synthesize and persist provenance-aware local knowledge",self.knowledge_acquirer.acquire,"external"); t.add("search_knowledge","Search locally acquired knowledge with provenance",self.knowledge_acquirer.search,"read")
        t.add("browser_recover","Recover a stale persistent browser session without replaying actions; independently verify fresh state",browser.recover,"execute"); t.add("browser_open","Open URL in persistent controlled Playwright browser",browser.open,"external"); t.add("browser_tabs","List persistent browser tabs",browser.tabs,"read"); t.add("browser_switch_tab","Switch persistent browser tab",browser.switch_tab,"execute"); t.add("browser_new_tab","Open a new persistent browser tab",browser.new_tab,"external"); t.add("browser_click_role","Click one browser element by semantic role/name; require expected_url or new expected_text",browser.click_role,"external"); t.add("browser_page_text","Read visible browser page text",browser.page_text,"read"); t.add("browser_snapshot","Inspect current browser state",browser.snapshot,"read"); t.add("browser_click_text","Click one exact visible browser text; require expected_url or new expected_text",browser.click_text,"external"); t.add("browser_fill","Fill labeled browser input",browser.fill,"external"); t.add("browser_press","Press a key on one focused browser control; require expected_url or new expected_text",browser.press,"external"); t.add("browser_screenshot","Capture controlled browser",browser.screenshot,"read")
        t.postconditions.register("browser_click_role",lambda args,result:verify_browser_click_postcondition(browser,args,result))
        t.postconditions.register("browser_click_text",lambda args,result:verify_browser_click_postcondition(browser,args,result))
        t.postconditions.register("browser_press",lambda args,result:verify_browser_click_postcondition(browser,args,result))
        t.add("run_windows_command","Run Windows command with permission",terminal.run,"system"); t.add("take_screenshot","Capture Windows screen",screenshot,"read"); t.add("ground_screen","Capture screen and detect whether it changed since the previous observation",grounder.capture,"read"); t.add("screen_state","Get the latest visual state metadata",grounder.state,"read"); t.add("discover_apps","Discover installed Windows applications matching a name",discovery.search,"read"); t.add("running_apps","Inspect currently running Windows processes",discovery.running,"read"); t.add("screen_size","Get screen resolution",pc.screen_size,"read"); t.add("mouse_position","Get mouse position",pc.mouse_position,"read")
        t.add("weather_lookup","Get current conditions for a location through Open-Meteo; reports location, observation time and source",weather.lookup,"external")
        t.add("public_ip_lookup","Look up the current public IP through ipify over HTTPS; the address is returned only and never persisted",public_ip.lookup,"external")
        t.add("battery_status","Read the current Windows battery percentage, charging state and remaining-time estimate",hardware.battery_status,"read")
        t.add("display_brightness","Read current brightness from each Windows WMI-capable display",hardware.brightness_status,"read")
        t.add("set_display_brightness","Set Windows display brightness from 0 to 100 and verify each display by fresh readback",hardware.set_brightness,"execute")
        t.add("system_volume","Read Windows default audio endpoint master volume",hardware.volume_status,"read")
        t.add("set_system_volume","Set Windows default audio endpoint master volume from 0 to 100 and verify fresh readback",hardware.set_volume,"execute")
        t.add("capture_camera_image","Capture one camera frame into ALICE workspace; requires explicit per-capture camera confirmation",camera.capture,"external")
        t.add("analyze_camera_image","Analyze an ALICE-captured camera frame with the configured vision backend after explicit confirmation; local-only mode must use a local model and must not upload the image",analyze_camera_image,"external")
        t.add("weather_lookup","Get current conditions for a location through Open-Meteo; reports location, observation time and source",weather.lookup,"external")
        t.add("battery_status","Read the current Windows battery percentage, charging state and remaining-time estimate",hardware.battery_status,"read")
        t.add("display_brightness","Read current brightness from each Windows WMI-capable display",hardware.brightness_status,"read")
        t.add("set_display_brightness","Set Windows display brightness from 0 to 100 and verify each display by fresh readback",hardware.set_brightness,"execute")
        t.add("system_volume","Read Windows default audio endpoint master volume",hardware.volume_status,"read")
        t.add("set_system_volume","Set Windows default audio endpoint master volume from 0 to 100 and verify fresh readback",hardware.set_volume,"execute")
        t.add("capture_camera_image","Capture one camera frame into ALICE workspace; requires explicit per-capture camera confirmation",camera.capture,"external")
        t.add("analyze_camera_image","Analyze an ALICE-captured camera frame; may share image with the configured model and requires explicit confirmation",analyze_camera_image,"external")
        for n,fn in [("move_mouse",pc.move),("click",pc.click),("double_click",pc.double_click),("scroll",pc.scroll),("type_text",pc.type_text),("press_key",pc.press),("hotkey",pc.hotkey),("drag",pc.drag)]: t.add(n,"Desktop interaction",fn,"execute")
        t.add("build_project","Build a software project with isolated pytest tests and independent on-disk output hash verification",builder.build,"write"); t.add("build_ai_agent","Build and test an AI agent in an isolated offline container, then verify generated files from disk",builder.build_ai_agent,"write"); t.add("generate_image","Generate an image using the configured image backend; hosted image APIs are blocked in local-only mode and this build has no local image generator",generate_image,"external"); t.add("capability_inventory","Show Alice learned and built capabilities",self.capabilities.inventory,"read"); t.add("integration_inventory","Show installed/available Alice integration surfaces",self.integrations.list,"read"); t.add("learn_skill","Research/build/validate a missing reusable capability",learn_skill,"write"); t.add("acquire_capability","Research, build, validate and activate a missing bounded capability, then continue the original task",acquire_capability,"write"); t.add("install_dependency","Install a named PyPI dependency when a capability needs it",deps.install,"system"); t.add("delegate_specialist","Reason with configured specialist models; local-only mode restricts this to local inference",delegate_specialist,"read"); t.add("multi_agent_task","Create temporary bounded specialist workers, merge their reports, verify evidence, and dispose workers",multi_agent_task,"write"); t.add("world_state","Inspect Alice’s compact local world model",self.world.snapshot,"read"); t.add("self_diagnostics","Run syntax and compile diagnostics",sm.diagnostics,"read"); t.add("self_snapshot","Create rollback snapshot",sm.snapshot,"write"); t.add("self_apply_patch","Apply a validated source change only inside alice/",sm.apply_patch,"write"); t.add("self_upgrade","Upgrade Alice by safely rewriting only necessary alice/ source files; backup, test and rollback automatically",sm.self_upgrade,"write"); t.add("self_modify","Analyze, implement, test and safely promote a requested ALICE source upgrade with rollback",sm.self_upgrade,"system"); t.add("self_repair","Diagnose, repair, test and rollback if necessary",sm.self_repair,"write"); t.add("self_update_git","Fast-forward update with rollback on failed tests",sm.update_from_git,"write");
        def schedule_package_upgrade(package_path):
            """Require publisher authentication before handing a ZIP to the helper."""
            if getattr(self,"_update_recovery_blocked",False):
                raise RuntimeError("Package updates are disabled because interrupted update recovery did not complete")
            package = os.path.abspath(os.path.expanduser(str(package_path)))
            updater = InPlaceUpdater(os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
            check = verify_signed_package(updater.root, package)
            old=version_tuple(self.updates.status().get("current_version","0.0")); new=version_tuple(check["manifest"]["version"])
            if old and new and old[0]!=new[0]:raise RuntimeError("Major ALICE updates require explicit Update Center approval")
            helper = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "deployment", "update_helper.py"))
            py = os.path.join(updater.root, ".venv", "Scripts", "python.exe")
            if not os.path.exists(py):
                py = sys.executable
            args = [py, helper, "--root", str(updater.root), "--package", package, "--pid", str(os.getpid()), "--restart"]
            flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            subprocess.Popen(args, cwd=str(updater.root), creationflags=flags)
            self._queue_ui("shutdown")
            return {"ok": True, "status": "update_scheduled", "target": check["manifest"]["version"], "message": "Alice will exit, apply the verified package, run the full test suite, and restart only if verification passes."}
        t.add("install_alice_update", "Apply a verified ALICE upgrade package to the existing installation, preserving protected user state and rolling back on test failure", schedule_package_upgrade, "system");
        t.add("check_alice_updates", "Check the configured ALICE stable update source for a newer verified release", lambda: self.updates.check(), "read");
        t.add("download_alice_update", "Download and verify the latest ALICE release without installing it", lambda: self.updates.check_and_download(), "write");
        t.add("android_devices","List connected Android devices through local ADB",mobile.devices,"read"); t.add("android_screenshot","Capture the connected Android screen",mobile.screenshot,"read"); t.add("android_mail_unread_count","Read only an unambiguous visible unread badge from foreground Gmail or Outlook; never reads message bodies and does not count mail received today",lambda serial:read_mail_unread_count(android_observer,serial),"read"); t.add("android_tap","Tap one uniquely observed Android control and verify an expected UI transition",android_tap,"execute"); t.add("android_swipe","Swipe on Android and verify a declared UI transition",android_swipe,"execute"); t.add("android_text","Type into the uniquely focused Android edit field and verify the exact appended text",android_text,"execute"); t.add("android_keyevent","Send an allowlisted Android key only with an observed expected UI transition",android_keyevent,"execute"); t.add("android_launch_app","Launch a package on the specified Android serial and independently verify it is foreground",android_launch_app,"execute"); t.add("android_shell","Run a command through Android ADB shell",mobile.shell,"system"); t.add("ai_council","Ask all configured AI providers and synthesize",self.router.council,"read")
        t.add("whatsapp_visible_chat","Verify the requested WhatsApp chat and inspect visible outgoing-message evidence through authorized Android UI",whatsapp_visible_chat,"read")
        t.add("whatsapp_send_reply","Send a WhatsApp reply only after scoped device consent and visible confirmation of the requested chat; verify the new outgoing message",whatsapp_send_reply,"external")
        t.add("device_graph_snapshot","List registered devices and advisory graph relationships; this never grants consent or control authority",device_graph_snapshot,"read")
        t.add("device_graph_link","Record a user-declared device relationship only; this does not pair devices or grant consent or control authority",device_graph_link,"write")
        return t

    def _queue_ui(self, kind, *payload):
        """Queue worker results for the Tk main thread. Never call Tk from workers."""
        self._ui_queue.put((kind, payload))

    def _drain_ui_queue(self):
        """Apply queued worker UI events on the Tk owner thread only.

        Streaming chunks are coalesced before touching the Text widget. This
        prevents a fast provider from flooding Tk with hundreds of insert/config
        operations and starving the event loop (which makes Windows report the
        window as Not Responding).
        """
        processed = 0
        pending = self._pending_ui_item
        self._pending_ui_item = None
        while processed < 60:
            try:
                item = pending if pending is not None else self._ui_queue.get_nowait()
                pending = None
            except queue.Empty:
                break
            kind, payload = item
            processed += 1
            try:
                if kind == "stream_append":
                    cancel_event, piece = payload
                    pieces = [str(piece)]
                    # Coalesce adjacent stream chunks so Tk performs one insert
                    # instead of one insert per provider token/chunk.
                    for _ in range(99):
                        try:
                            nxt = self._ui_queue.get_nowait()
                        except queue.Empty:
                            break
                        if nxt[0] == "stream_append" and nxt[1][0] is cancel_event:
                            pieces.append(str(nxt[1][1]))
                        else:
                            pending = nxt
                            break
                    self._stream_append(cancel_event, "".join(pieces))
                elif kind == "stream_start":
                    self._stream_start(*payload)
                elif kind == "toggle_window":
                    self.toggle_window()
                elif kind == "mini_hotkey":
                    if self._mini_window is not None and self._mini_window.winfo_exists() and self._mini_window.winfo_viewable():
                        self._mini_window.withdraw()
                    else:self._mini_voice_start()
                elif kind == "tray_open_mini":
                    self._open_mini_chat(payload[0] if payload else None)
                elif kind == "tray_open_workspace":
                    self._open_full_workspace()
                elif kind == "finish":
                    self.finish(*payload)
                elif kind == "premium_submit":
                    self._submit_text(payload[0],source="premium")
                elif kind == "premium_provider_setup":
                    self.provider_setup()
                elif kind == "premium_provider_saved":
                    if payload:
                        try:self.activity.config(text=str(payload[0]))
                        except Exception:pass
                elif kind == "premium_native_panel":
                    panel=str(payload[0]) if payload else ""
                    self.root.deiconify(); self.root.lift()
                    actions={"updates":self.update_center,"voice":self.audio_center,
                        "goals":self.show_goals,"approvals":self.show_approvals,
                        "devour":self.show_devour_review,"history":self.show_history,
                        "brain":self.provider_setup}
                    if panel=="tools":
                        try:self.tools_menu.tk_popup(self.root.winfo_pointerx(),self.root.winfo_pointery())
                        finally:self.tools_menu.grab_release()
                    elif panel in actions:actions[panel]()
                elif kind == "premium_minimize_to_mini":
                    self._open_mini_chat()
                elif kind == "mini_file_dropped":
                    self._handle_mini_file_drop(payload[0] if payload else [])
                elif kind == "premium_speak_mode":
                    enabled=bool(payload[0]) if payload else False
                    self.voice.set_enabled(enabled)
                    self.text_mode=not enabled
                    self._update_menu_labels()
                    self._publish_premium_event("mode",{"speak_mode":enabled})
                elif kind == "orb_state":
                    self._set_orb_state(payload[0] if payload else "idle")
                elif kind == "shutdown":
                    self.shutdown()
                elif kind == "heard":
                    self._handle_heard(*payload)
                elif kind == "heard_error":
                    self._handle_heard_error(*payload)
                elif kind == "jarvis_status":
                    if not self._shutdown:self.activity.config(text=str(payload[0]))
                elif kind == "jarvis_transcript":
                    self._handle_jarvis_transcript(*payload)
                elif kind == "jarvis_partial":
                    if not self._shutdown:
                        preview=str(payload[0] or "").strip()
                        self.activity.config(text=("Listening • "+preview[:180]) if preview else "Listening; phrase sent to ALICE.")
                        if preview and self._mini_window is not None and self._mini_window.winfo_viewable():
                            self._mini_canvas.itemconfigure(self._mini_response_label,text=preview[:160])
                elif kind == "history":
                    self.show_history()
                elif kind == "mic_test":
                    self._apply_mic_test(*payload)
                elif kind == "voice_status":
                    self._apply_voice_status(*payload)
                elif kind == "voice_test":
                    self._apply_voice_test(*payload)
                elif kind == "fish_audio_test":
                    label,result=payload
                    if label.winfo_exists():
                        label.config(text=("Fish Audio playback test passed." if result.get("ok") else
                                          "Fish Audio playback test failed: "+str(result.get("error") or "no playable audio")))
                elif kind == "provider_test":
                    label, text = payload
                    label.config(text=str(text))
                elif kind == "update_check":
                    self._apply_update_check(*payload)
                elif kind == "update_ready":
                    self._confirm_and_schedule_update(payload[0])
                elif kind == "goal_run_complete":
                    self._apply_goal_run_complete(*payload)
                elif kind == "devour_candidate_complete":
                    self._apply_devour_candidate_complete(*payload)
            except Exception as exc:
                try:
                    self._log_ui_error(exc)
                except Exception:
                    pass
        if pending is not None:
            self._pending_ui_item = pending
        if not self._shutdown:
            self.root.after(75, self._drain_ui_queue)

    def _log_ui_error(self, exc):
        try:
            self.chat.config(state="normal")
            self.chat.insert("end", "\n[UI error: "+str(exc)+"]\n\n")
            self.chat.config(state="disabled")
            self.chat.see("end")
        except Exception:
            pass

    def _stream_start(self, cancel_event):
        if self._cancel_event is not cancel_event or cancel_event.is_set(): return
        self._stream_event=cancel_event; self._streaming=True
        self._publish_premium_event("stream_start", "")
        self._mini_refresh_history()
        self.chat.config(state="normal")
        self.chat.insert("end", "Alice: ")
        self.chat.see("end")
        self.chat.config(state="disabled")
        if self._hud_chatbox is not None:self._hud_chatbox.begin_stream()

    def _stream_append(self, cancel_event, piece):
        if self._cancel_event is not cancel_event or cancel_event.is_set() or not self._streaming: return
        self._publish_premium_event("stream_delta", str(piece))
        self.chat.config(state="normal")
        self.chat.insert("end", str(piece))
        self.chat.see("end")
        self.chat.config(state="disabled")
        if self._hud_chatbox is not None:self._hud_chatbox.stream(piece)
        self._mini_refresh_history()

    def _stream_end(self, cancel_event):
        if self._stream_event is cancel_event and self._streaming:
            self._publish_premium_event("stream_end", "")
            self.chat.config(state="normal")
            self.chat.insert("end", "\n\n")
            self.chat.see("end")
            self.chat.config(state="disabled")
            if self._hud_chatbox is not None:self._hud_chatbox.end_stream()
            self._streaming=False; self._stream_event=None

    def say(self,speaker,text):
        if text is None or text == "": return
        self._publish_premium_event("message", {"speaker":str(speaker),"text":str(text)})
        if str(speaker).lower()=="alice":self._publish_orb_state("response")
        elif str(speaker).lower()=="you":self._publish_orb_state("awake")
        self.chat.config(state="normal"); self.chat.insert("end",f"{speaker}: {text}\n\n"); self.chat.see("end"); self.chat.config(state="disabled")
        if self._hud_chatbox is not None:self._hud_chatbox.append(speaker,text)
        self._mini_refresh_history()

    def _publish_orb_state(self,state):
        """Drive ALICE's floating orb and forward activity to the workspace UI."""
        self._queue_ui("orb_state",str(state))
        self._publish_premium_event("orb_state",{"state":str(state)})

    def _publish_premium_event(self, kind, payload):
        """Keep a bounded, thread-safe event stream for the bundled WebView."""
        lock=getattr(self,"_premium_event_lock",None)
        if lock is None:return
        with lock:
            self._premium_event_seq+=1
            self._premium_events.append({"id":self._premium_event_seq,"type":kind,"data":payload,
                "timestamp":datetime.now(timezone.utc).isoformat(timespec="seconds")})
            if len(self._premium_events)>500:self._premium_events=self._premium_events[-500:]

    @staticmethod
    def _is_hypothetical_analysis(text):
        """Keep hypothetical/security/design questions in conversation mode.

        Phrases such as 'suppose', 'if a repo contains', 'what would you do', and
        explicit 'do not execute' instructions are analysis, not authorization to
        perform the described action.
        """
        s=" ".join(str(text).lower().split())
        markers=("suppose ","hypothetically","hypothetical","if a repo","if the repo","if a devoured","what would you do","what exactly would you do","should alice","should she","would you blindly","do not execute","don't execute","do not modify","don't modify","explain the security decision")
        return any(m in s for m in markers)

    @staticmethod
    def _is_stop_voice_command(text):
        s=" ".join(str(text).lower().split())
        return any(x in s for x in ("stop talking", "stop speaking", "stop voice", "stop the voice", "stop the sound", "be quiet", "silence alice", "give me text only", "text only"))

    @staticmethod
    def _is_voice_disable_command(text):
        s=" ".join(str(text).lower().split())
        return s in {"turn off sound","turn off voice","voice off","disable voice","disable alice voice","mute alice","mute alice voice","stop alice voice"}

    @staticmethod
    def _is_voice_enable_command(text):
        s=" ".join(str(text).lower().split())
        return s in {"turn on sound","turn on voice","voice on","enable voice","enable alice voice","unmute alice","unmute alice voice"}

    @staticmethod
    def _needs_tools(text):
        s=text.lower()
        if is_trading_request(text):
            return True
        task_terms=("assimilate ","devour ","repository ","github.com","self data","own code","own data","local ai","offline ","open ","close ","click ","press ","type ","move ","scroll ","drag ","launch ","run ","install ","download ","upload ","create a file","save ","delete ","rename ","copy ","move file","browser","website","web page","screenshot","screen","desktop","laptop","computer","phone","android","whatsapp","email","send ","message ","build ","modify ","change your","change alice","upgrade yourself","repair yourself","self upgrade","learn how to","perform ","do this for me","make a presentation","make a spreadsheet","make a document")
        return any(term in s for term in task_terms)

    @staticmethod
    def _wants_voice(text):
        s=" ".join(str(text).lower().split())
        return any(x in s for x in ("with voice", "using voice", "say it", "read it", "read this", "speak it", "speak this", "out loud", "aloud", "verbally", "tell me verbally"))

    def read_last(self):
        if not self.last_response:
            self.say("Alice", "There is no response to read yet.")
            return
        self.voice.speak_async(self.last_response, replace_pending=True)
        self.activity.config(text=self.provider_status()+" • speaking")

    def _update_menu_labels(self):
        try:self.tools_menu.entryconfigure(self.text_menu_index,label="Text: ON" if self.text_mode else "Text: OFF"); self.tools_menu.entryconfigure(self.concise_menu_index,label="Concise: ON" if self.concise_mode else "Concise: OFF")
        except Exception:pass
        try:self._bubble_menu.entryconfigure(3,label="Text: ON" if self.text_mode else "Text: OFF"); self._bubble_menu.entryconfigure(4,label="Concise: ON" if self.concise_mode else "Concise: OFF")
        except Exception:pass
    def toggle_text_mode(self):
        self.text_mode=not self.text_mode; self._update_menu_labels(); self.say("Alice", "Text responses enabled." if self.text_mode else "Text responses disabled; voice output may be used when enabled.")
    def toggle_concise(self):
        self.concise_mode=not self.concise_mode; self._update_menu_labels(); self.say("Alice", "Concise mode enabled." if self.concise_mode else "Normal explanation mode enabled.")

    @staticmethod
    def _is_self_engineering_request(text):
        s=" ".join(str(text).lower().split())
        explicit_phrases = any(x in s for x in (
            "improve yourself", "improve alice", "evolve yourself", "evolve alice",
            "modify yourself", "modify alice", "build this capability yourself",
            "add this capability to yourself", "upgrade yourself to", "upgrade alice to",
            "make yourself better", "make alice better", "learn to do this yourself",
        ))
        if explicit_phrases:
            return True
        # A direct feature request addressed to ALICE should enter the governed
        # self-engineering route whether it came from typed chat or a speech
        # transcript. Keep this narrow so ordinary feature-design discussion
        # does not trigger source changes.
        return bool(
            re.search(r"\b(?:i want|please|can you|could you|alice should|alice,?)\b.{0,100}"
                      r"\b(?:alice\s+)?(?:to\s+)?(?:develop|build|add|implement|create|code)\b.{0,120}"
                      r"\b(?:yourself|herself|into yourself|into alice|to alice|for yourself|feature|capability)\b", s)
            or re.search(r"\b(?:develop|build|add|implement|create|code)\b.{0,80}"
                         r"\b(?:this|that|a|the)\s+(?:new\s+)?(?:feature|capability)\b.{0,80}"
                         r"\b(?:yourself|for alice|into alice)\b", s)
        )

    @staticmethod
    def _is_update_request(text):
        s=" ".join(str(text).lower().split())
        return any(x in s for x in (
            "update yourself", "update alice", "upgrade yourself", "upgrade alice",
            "check for updates", "check for an update", "latest alice update",
            "latest stable build", "install the latest alice", "install latest alice",
        ))

    def _wants_update_install(self, text):
        s=" ".join(str(text).lower().split())
        return any(x in s for x in ("update yourself", "update alice", "upgrade yourself", "upgrade alice", "install the latest alice", "install latest alice"))

    def _perform_update_request(self, text):
        """Network/download work for self-update; UI confirmation happens on Tk thread."""
        try:
            info=self.updates.check()
            if not self._wants_update_install(text):
                if info.get("available"):
                    return {"status":"completed","result":f"Stable update {info.get('latest_version')} is available. I have not downloaded or installed it."}
                if info.get("configured"):
                    return {"status":"completed","result":f"I checked my stable update source. I am already on {info.get('current_version')}."}
                return {"status":"completed","result":info.get("message","No update source configured.")}
            if not info.get("configured"):
                return {"status":"completed","result":"I can self-update now, but my stable update source is not configured yet. Set ALICE_UPDATE_REPO to your release repository or ALICE_UPDATE_FEED_URL to your HTTPS release feed once; after that I can check, download, verify, install, test, restart, and roll back updates myself."}
            if not info.get("available"):
                return {"status":"completed","result":f"I checked my stable update source. I am already on {info.get('current_version')}."}
            downloaded=self.updates.download(info)
            if self.updates.status().get("auto_install"):
                package=downloaded.get("package")
                if package and os.path.isfile(package):
                    scheduled=self._schedule_package_upgrade(package)
                    return {"status":"completed","result":scheduled.get("message",f"Verified update {downloaded.get('latest_version')} scheduled."),"streamed":False}
            return {"status":"update_ready","update":downloaded,"result":f"A verified stable update {downloaded.get('latest_version')} is ready. I downloaded it and verified its SHA-256. I can install it after you approve the restart."}
        except Exception as exc:
            return {"status":"failed","error":str(exc)}

    def _confirm_and_schedule_update(self, info):
        if self._shutdown:return
        target=str(info.get("latest_version","the latest version")); package=str(info.get("package", ""))
        if not package or not os.path.isfile(package):
            self.say("Alice","The verified update package is no longer available locally. I won't install an incomplete update."); return
        ok=messagebox.askyesno("ALICE self-update", f"Verified update {target} is ready.\n\nAlice will:\n• create a rollback backup\n• close safely\n• install the update\n• run the complete test suite\n• restart only if verification passes\n• roll back automatically if verification fails\n\nInstall now?")
        if not ok:
            self.say("Alice","Update kept downloaded and verified. I did not install it."); return
        try:
            result=self._schedule_package_upgrade(package)
            self.say("Alice",result.get("message","Update scheduled."))
        except Exception as exc:
            self.say("Alice","I did not start the update: "+str(exc))

    def _self_engineer_and_schedule(self, sm, goal):
        """Run governed self-engineering, then hand the verified package to the external updater."""
        result = sm.prepare_self_upgrade(goal, repair_attempts=2)
        if not result.get("ok"):
            return result
        package = result.get("package")
        if not package or not os.path.isfile(package):
            raise RuntimeError("Self-engineering produced no verified upgrade package")
        scheduled = self._schedule_package_upgrade(package)
        result["status"] = "update_scheduled"
        result["schedule"] = scheduled
        result["message"] = (
            f"I engineered and tested {result.get('target_version')}. "
            "The verified package is now with my external updater; I will close, "
            "install it, run the full suite again, and roll back automatically if anything fails."
        )
        return result

    def _schedule_package_upgrade(self, package_path, *, approved_major=False):
        if getattr(self,"_update_recovery_blocked",False):
            raise RuntimeError("Package updates are disabled because interrupted update recovery did not complete")
        package=os.path.abspath(os.path.expanduser(str(package_path)))
        root=str(self.root_path)
        check=verify_signed_package(root,package)
        current=version_tuple(self.updates.status().get("current_version","0.0"))
        target=version_tuple(check["manifest"]["version"])
        if current and target and current[0] != target[0] and not approved_major:
            raise RuntimeError("Major ALICE updates require an explicit Update Center approval")
        helper=os.path.join(root,"alice","deployment","update_helper.py")
        py=os.path.join(root,".venv","Scripts","python.exe")
        if not os.path.exists(py):py=sys.executable
        args=[py,helper,"--root",root,"--package",package,"--pid",str(os.getpid()),"--restart"]
        flags=getattr(subprocess,"DETACHED_PROCESS",0)|getattr(subprocess,"CREATE_NEW_PROCESS_GROUP",0)
        subprocess.Popen(args,cwd=root,creationflags=flags)
        self._queue_ui("shutdown")
        return {"ok":True,"target":check["manifest"]["version"],"message":"Update helper started. Alice will close, verify the package, run the full test suite, restart only after success, and keep the rollback backup if recovery is needed."}

    def update_center(self):
        win=tk.Toplevel(self.root); win.title("Alice Update Center"); win.geometry("760x500"); win.transient(self.root); win.grab_set()
        tk.Label(win,text="Alice Update Center",font=("Segoe UI",16,"bold")).pack(anchor="w",padx=16,pady=(16,6))
        tk.Label(win,text="Updates require an Ed25519 signature from a publisher key you explicitly trust. SHA-256 alone is not publisher authentication. Signed packages are staged and test-gated before installation.",wraplength=720,justify="left").pack(anchor="w",padx=16)
        form=tk.Frame(win); form.pack(fill="x",padx=16,pady=12)
        tk.Label(form,text="GitHub repo (owner/name):").grid(row=0,column=0,sticky="w",pady=5)
        repo=tk.Entry(form); repo.insert(0,self.updates.status().get("repo", "")); repo.grid(row=0,column=1,sticky="ew",pady=5)
        tk.Label(form,text="HTTPS feed URL (optional):").grid(row=1,column=0,sticky="w",pady=5)
        feed=tk.Entry(form); feed.insert(0,self.updates.status().get("feed_url", "")); feed.grid(row=1,column=1,sticky="ew",pady=5)
        form.columnconfigure(1,weight=1)
        local_frame=tk.LabelFrame(win,text="Local ZIP upgrade",padx=10,pady=8); local_frame.pack(fill="x",padx=16,pady=(2,8))
        local_var=tk.StringVar(value=self.updates.status().get("local_zip", ""))
        local_entry=tk.Entry(local_frame,textvariable=local_var); local_entry.pack(side="left",fill="x",expand=True,padx=(0,6))
        def browse_local():
            path=filedialog.askopenfilename(parent=win,title="Select ALICE upgrade ZIP",filetypes=[("ALICE upgrade ZIP","*.zip"),("ZIP files","*.zip"),("All files","*.*")])
            if path: local_var.set(path)
        tk.Button(local_frame,text="Browse ZIP...",command=browse_local,width=14).pack(side="left")
        local_auto=tk.BooleanVar(value=bool(self.updates.status().get("auto_install_local",False)))
        tk.Checkbutton(win,text="Automatically install this verified local ZIP when a newer version is detected (12-hour check)",variable=local_auto).pack(anchor="w",padx=16,pady=(0,5))
        auto_var=tk.BooleanVar(value=bool(self.updates.status().get("auto_install",False)))
        tk.Checkbutton(win,text="Automatically install verified stable remote updates (12-hour check)",variable=auto_var).pack(anchor="w",padx=16,pady=(0,6))
        status=tk.Label(win,text="",anchor="w",wraplength=720,justify="left"); status.pack(fill="x",padx=16,pady=5)
        def trust_publisher_key():
            key_path=filedialog.askopenfilename(parent=win,title="Select ALICE publisher Ed25519 public key",filetypes=[("Public key files","*.pub *.pem *.txt *.key"),("All files","*.*")])
            if not key_path:return
            try:
                public=public_key_from_file(key_path)
                fingerprint=__import__("hashlib").sha256(public).hexdigest()
                accepted=messagebox.askyesno("Trust ALICE publisher key?",f"Compare this full SHA-256 fingerprint with the publisher's independently obtained fingerprint before trusting it:\n\n{fingerprint}\n\nTrust this signing key on this installation?",parent=win)
                if not accepted:return
                enroll_trusted_key(self.root_path,public,fingerprint)
                status.config(text=f"Trusted publisher key {fingerprint}. Keep the fingerprint with your release records.")
            except Exception as exc:status.config(text="Publisher key rejected: "+str(exc))
        tk.Button(win,text="Trust publisher key…",command=trust_publisher_key,width=20).pack(anchor="w",padx=16,pady=(4,0))
        def save():
            try:
                self.updates.configure(repo=repo.get().strip(),feed_url=feed.get().strip(),local_zip=local_var.get().strip(),auto_check=True,auto_install=auto_var.get(),auto_install_local=local_auto.get())
                status.config(text="Saved. Updates remain unavailable until a trusted publisher key and signed manifest are present. Automatic installation defaults off.")
            except Exception as exc: status.config(text="Could not save: "+str(exc))
        def install_local():
            package=local_var.get().strip()
            if not package or not os.path.isfile(package):
                status.config(text="Select an existing ALICE .zip package first."); return
            try:
                check=self.updates.check_local(package)
                target=check["latest_version"]
                current=self.updates.status().get("current_version")
                if target and __import__('alice.deployment.updater',fromlist=['version_tuple']).version_tuple(target) <= __import__('alice.deployment.updater',fromlist=['version_tuple']).version_tuple(current):
                    status.config(text=f"Refusing non-forward package: installed {current}, selected {target}."); return
                current_tuple=__import__('alice.deployment.updater',fromlist=['version_tuple']).version_tuple(current)
                target_tuple=__import__('alice.deployment.updater',fromlist=['version_tuple']).version_tuple(target)
                approved_major=False
                if current_tuple and target_tuple and current_tuple[0]!=target_tuple[0]:
                    if not messagebox.askyesno("Approve major ALICE update?",f"This signed update changes the major version from {current} to {target}. Continue?",parent=win):return
                    approved_major=True
                result=self._schedule_package_upgrade(package,approved_major=approved_major)
                status.config(text=result.get("message","Verified local upgrade scheduled. Alice will close and restart after tests pass."))
                win.after(500,win.destroy)
            except Exception as exc: status.config(text="Local ZIP rejected: "+str(exc))
        def check_remote():
            def work():
                try:r=self.updates.check(); self._queue_ui("update_check",r)
                except Exception as exc:self._queue_ui("update_check",{"ok":False,"error":str(exc)})
            threading.Thread(target=work,daemon=True,name="AliceUpdateCheck").start()
        def check_local():
            package=local_var.get().strip()
            if not package or not os.path.isfile(package): status.config(text="Select an existing ALICE .zip package first."); return
            try:
                r=self.updates.check_local(package)
                status.config(text=f"SIGNED PACKAGE VERIFIED — {r.get('latest_version')} | sequence {r.get('sequence')} | {r.get('file_count')} files | publisher {r.get('fingerprint')}.")
            except Exception as exc: status.config(text="Local ZIP rejected: "+str(exc))
        buttons=tk.Frame(win); buttons.pack(fill="x",padx=16,pady=10)
        tk.Button(buttons,text="Save source",command=save,width=14).pack(side="left",padx=(0,5))
        tk.Button(buttons,text="Check remote",command=check_remote,width=14).pack(side="left",padx=5)
        tk.Button(buttons,text="Validate ZIP",command=check_local,width=14).pack(side="left",padx=5)
        tk.Button(buttons,text="Install ZIP",command=install_local,width=14).pack(side="left",padx=5)
        tk.Button(buttons,text="Close",command=win.destroy,width=10).pack(side="right")

    @staticmethod
    def _is_shutdown_command(text):
        """Recognize direct local shutdown commands without consulting the AI.

        These commands are intentionally narrow: they must clearly address Alice
        or be a standalone shutdown/exit command. Matching happens before any
        network call, tool planning, streaming, or text-to-speech.
        """
        s=" ".join(str(text).strip().lower().split())
        return s in {
            "shutdown", "shut down", "exit", "quit", "close", "close alice",
            "goodbye", "bye", "turn off", "turn off alice",
            "alice shutdown", "alice shut down", "shutdown alice",
            "alice turn off", "alice exit", "alice quit", "goodbye alice",
            "bye alice",
        }

    def send(self):
        self._sync_message_from_native()
        self._submit_text(self.entry.get(),source="main")

    def _submit_text(self,raw_text,source="main"):
        text=str(raw_text or "").strip()
        if not text:return
        _, contains_credential = redact_secrets(text)
        if contains_credential:
            if source=="main":self.entry.delete(0,"end"); self._sync_message_to_native()
            self.say("Alice","I blocked this message because it looks like it contains an API key or credential. It was not sent or saved. Enter keys in Brain Setup only. If this was a real key you already sent in an earlier chat, revoke it in the provider's dashboard.")
            return
        if self._is_shutdown_command(text):
            # Local control command: no LLM request and no TTS. Stop immediately.
            if source=="main":self.entry.delete(0,"end"); self._sync_message_to_native()
            self._last_request_text=text
            self.shutdown()
            return
        if self._cancel_event is not None and not self._cancel_event.is_set(): self.stop_current(silent=True)
        else:
            try:self.voice.stop()
            except Exception:pass
        if source=="main":self.entry.delete(0,"end"); self._sync_message_to_native(); self._focus_message_entry()
        elif self._hud_chatbox is not None:self._hud_chatbox.focus_input()
        self.say("You",text); self.activity.config(text="Alice is working..."); self.stop_button.config(state="normal")
        self._publish_orb_state("thinking")
        self._last_request_text=text
        cancel_event=threading.Event(); self._cancel_event=cancel_event
        threading.Thread(target=self.worker,args=(text,cancel_event),daemon=True).start()

    def stop_current(self,silent=False):
        ev=self._cancel_event
        if ev is not None: ev.set()
        self._cancel_event=None; self.stop_button.config(state="disabled"); self.activity.config(text=self.provider_status()+" • stopped")
        try:self.voice.stop()
        except Exception:pass
        self._publish_orb_state("idle")
        if not silent:self.say("Alice","Stopped. I won't display the result of the current request.")

    @staticmethod
    def _gluttony_url(text):
        import re
        m=re.search(r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?",str(text))
        return m.group(0) if m else None

    @staticmethod
    def _devour_local_source(text):
        import re
        raw=str(text).strip().strip('"\'')
        # Prefer a Windows absolute path ending in .zip or a directory path when it exists.
        candidates=re.findall(r'"([^"\n]+)"|\'([^\'\n]+)\'|(?:[A-Za-z]:[\\/][^\s"\']+|/[^\s"\']+)', raw)
        flattened=[]
        for a,b,c in candidates:
            flattened.append(a or b or c)
        for c in flattened:
            c=c.rstrip('.,;')
            if os.path.exists(os.path.expanduser(c)):
                return c
        return None

    def _stored_devour_answer(self, text):
        """Answer explicit questions about the stored latest Devour report deterministically.

        The conversational model should not be asked to reconstruct structured report
        fields from memory. This path reads the persisted digest and returns the exact
        stored values for Claw-Code/report queries without performing a new Devour.
        """
        low=" ".join(str(text).lower().split())
        if "devour" not in low or "claw-code" not in low:
            return None
        try:
            report=self.devour.latest_report()
            if not report.get("ok"):
                return "No stored Devour report is available yet. No new Devour was performed."
            source=str(report.get("source") or "")
            if "claw-code" not in source.lower() and "claw-code" not in str(report.get("report") or "").lower():
                return None
            caps=report.get("capability_candidates") or []
            assessment=report.get("alice_capability_assessment") or {}
            security=report.get("security") or {}
            license_info=report.get("license") or {}
            counts={k:sum(1 for row in (assessment.get("capabilities") or []) if str(row.get("status",""))==k) for k in ("exists","partial","missing","unknown")}
            wants_all=("all three" in low or ("static security findings" in low and "8 main capabilities" in low and "comparison" in low))
            if wants_all:
                names=[str(c.get("name") or "") for c in caps]
                return (f"1. Static security findings: {security.get('threat_count',0)}\n"
                        f"2. Identified capabilities ({len(names)}): {', '.join(names)}\n"
                        f"3. Capability comparison: {counts['exists']} existing, {counts['partial']} partial, {counts['missing']} missing.\n"
                        "No new Devour was performed.")
            if "static security finding" in low or "security findings" in low:
                return f"The stored Claw-Code Devour report contains {security.get('threat_count',0)} static security findings. No new Devour was performed."
            if "8 main capabilities" in low or ("list" in low and "capabilit" in low):
                names=[str(c.get("name") or "") for c in caps]
                return "The stored Claw-Code Devour report identified: " + "; ".join(names) + ". No new Devour was performed."
            if "comparison" in low or "already existed" in low or "existing, were partial" in low:
                return (f"Stored Claw-Code comparison: {counts['exists']} existing, {counts['partial']} partial, "
                        f"{counts['missing']} missing. No new Devour was performed.")
            if "license" in low:
                return f"The stored Claw-Code Devour report identified the license as {license_info.get('kind','unknown')}. No new Devour was performed."
            if "source url" in low or "repository url" in low or "exact github repository" in low:
                return f"The stored Devour report lists the source as: {source}\nNo new Devour was performed."
        except Exception as exc:
            return f"I could not read the stored Devour report safely: {str(exc)[:240]}"
        return None

    def _direct_local_command(self,text):
        low=" ".join(str(text).lower().split())
        stored_devour=self._stored_devour_answer(text)
        if stored_devour is not None:
            return stored_devour
        if self._is_stop_voice_command(text):
            try:self.voice.set_enabled(False)
            except Exception:
                try:self.voice.stop()
                except Exception:pass
            self.text_mode=True; self._update_menu_labels()
            return "Voice stopped. I will return text only until voice is enabled again."
        if self._is_voice_disable_command(text):
            try:self.voice.set_enabled(False)
            except Exception:
                try:self.voice.stop()
                except Exception:pass
            self.text_mode=True; self._update_menu_labels()
            return "ALICE voice is off. I will continue responding with text."
        if self._is_voice_enable_command(text):
            try:self.voice.set_enabled(True)
            except Exception:pass
            self.text_mode=False; self._update_menu_labels()
            return "ALICE voice is on."
        if any(x in low for x in ("install alice upgrade", "install this alice upgrade", "apply alice upgrade", "install this upgrade")) and ".zip" in low:
            package=self._devour_local_source(text)
            if package and package.lower().endswith(".zip"):
                scheduled=self._schedule_package_upgrade(package)
                return scheduled.get("message", "The verified ALICE upgrade was scheduled.")
        if low in {"history","show history","open history","show conversation history","conversation history","show my history"}:
            self._queue_ui("history")
            return "Opening my stored conversation history."
        if low in {"audio status","microphone status","mic status","check microphone","check my microphone"}:
            st=self.microphone.status(); selected=(st.get("selected") or {}).get("name","none")
            if not st.get("speech_recognition") or not st.get("sounddevice"):
                return f"Microphone capture is not fully installed yet. SpeechRecognition={st.get('speech_recognition')}; sounddevice={st.get('sounddevice')}. Selected input: {selected}."
            return f"Microphone input is ready. Selected device: {selected}. {st.get('device_count',0)} input devices detected."
        url=self._gluttony_url(text)
        local_source=self._devour_local_source(text)
        source=url or local_source
        if source and any(k in low for k in ("assimilate","devour","eat","study","ingest")):
            wants_upgrade=any(k in low for k in ("upgrade myself","upgrade yourself","reimplement and upgrade","absorb and upgrade","install the useful capabilities"))
            if wants_upgrade:
                result=self.devour.devour(source, goal=text)
                assessment=result.get("alice_capability_assessment",{})
                names=[str(row.get("name","")) for row in assessment.get("capabilities",[]) if row.get("recommendation") in {"improve_native_capability","reimplement_natively"}]
                return (f"I analyzed {source} in quarantine without executing or installing its code. "
                        f"The report is {result['report']}. No native changes or upgrade were created. "
                        f"Review individual capabilities in Tools → DEVOUR Review before requesting a candidate. "
                        f"Candidates for native review: {', '.join(names) if names else 'none'}.")
            result=self.devour.devour(source); assessment=result.get("alice_capability_assessment",{}); rows=assessment.get("capabilities",[])
            counts={k:sum(1 for r in rows if r.get("status")==k) for k in ("exists","partial","missing","unknown")}; recommended=assessment.get("recommended_for_native_review",[])
            return (f"I devoured {source} into quarantine without executing external code. I found {len(result.get('capabilities',[]))} candidate capabilities and {result.get('security',{}).get('threat_count',0)} static findings. "
                    f"ALICE comparison: {counts['exists']} already exist, {counts['partial']} are partial, {counts['missing']} are missing. "
                    f"Recommended native review: {', '.join(recommended) if recommended else 'none'}. Digest: {result['report']}. Review the comparison before requesting native reimplementation and upgrade.")
        if any(k in low for k in ("my own data","your own data","your code","own code","self data")):
            status=self._self_status_text()
            return status
        if "local ai" in low or "offline" in low or "without api key" in low:
            # Deterministic status path: this remains usable even when no remote
            # model is configured.
            import shutil, socket
            installed=bool(shutil.which("ollama")); reachable=False
            try:
                host=os.getenv("OLLAMA_HOST","127.0.0.1:11434").replace("http://","").replace("https://","").split("/",1)[0]
                h,port=host.rsplit(":",1)
                with socket.create_connection((h,int(port)),timeout=0.5): reachable=True
            except Exception: pass
            if installed and reachable:
                self.router.reload_config()
                return "Local API-key-free reasoning is available through the detected OpenAI-compatible local service. I can use it without OpenRouter."
            return "I can reason without OpenRouter only when a local model is installed and running. Ollama was not detected as a reachable local service."
        return None

    def _self_status_text(self):
        sm=SelfManager(root=self.root_path,router=self.router)
        st=sm.workspace_status(); inv=sm.source_inventory()
        return f"I can inspect my own non-protected source and durable workspace. I currently have {inv['count']} inspectable source files. Protected security/permission files remain guarded. Workspace status: {st['state']}"

    def _perform_web_research(self, request, query, cancel_event=None):
        """Use fetched, citation-checked pages for app research answers."""
        if cancel_event is not None and cancel_event.is_set():
            return None
        acquired=self.knowledge_acquirer.acquire(query,max_sources=5)
        if cancel_event is not None and cancel_event.is_set():
            return None
        receipt=None
        if acquired.get("ok") is True:
            receipt=self.knowledge_acquirer.verify_acquisition_postcondition(
                {"topic":query},acquired)
        verified=bool(receipt and receipt.ok)
        if acquired.get("ok") is True and not verified:
            conclusion=str(acquired.get("conclusion") or "")
            bibliography=conclusion.partition("\n\nSources:\n")[2]
            answer=("I retrieved source pages, but the saved-evidence verification did not pass, "
                    "so I’m withholding the summary.")
            if bibliography:
                answer+="\n\nSources:\n"+bibliography
        else:
            answer=str(acquired.get("conclusion") or
                       "I could not produce a sourced answer for that request.")
        return {"status":"completed","result":answer,"streamed":False,
                "web_research":True,"research_status":str(acquired.get("status") or "unknown"),
                "research_verified":verified}

    def worker(self,text,cancel_event):
        try:
            # Persistence/learning stays off the Tk thread.
            self.conversation.append("user", text)
            self.memory.learn_from_chat(text)
            self.memory.learn_explicit(text)
            # Analysis-only/hypothetical questions must be classified before
            # cognitive/action routing. Otherwise words such as "delete",
            # "execute", "upgrade", or "devour" inside a hypothetical can
            # accidentally enter an approval or engineering path.
            # Explicit read-only research can include safety constraints such
            # as “do not modify files”. Those constraints must not divert the
            # request into local chat/model inference before the web route.
            explicit_web_search = getattr(
                getattr(self, "intent_router", None),
                "is_explicit_web_search", lambda _text: False
            )(text)
            if self._is_hypothetical_analysis(text) and not explicit_web_search:
                tx=ResponseTransaction()
                self._queue_ui("stream_start", cancel_event)
                try:
                    for piece in self.agent.respond_text_stream(text,concise=self.concise_mode,cancel_event=cancel_event,history=self._history_prompt()):
                        if cancel_event.is_set(): return
                        tx.append(piece); self._queue_ui("stream_append", cancel_event, piece)
                    state=tx.complete()
                    if not state.completed and not cancel_event.is_set():
                        fallback=self.agent.respond_text(text,concise=self.concise_mode,cancel_event=cancel_event,history=self._history_prompt()).strip()
                        if fallback:
                            tx.append(fallback); self._queue_ui("stream_append", cancel_event, fallback); state=tx.complete()
                except Exception as exc:
                    if cancel_event.is_set(): return
                    state=tx.fail(recoverable=True)
                    if state.recoverable:
                        continuation=self.agent.respond_text_recovery(text,state.text,concise=self.concise_mode,cancel_event=cancel_event,history=self._history_prompt()).strip()
                        if continuation:
                            tx.append(continuation); self._queue_ui("stream_append", cancel_event, continuation)
                            state=tx.complete()
                    if not state.completed:
                        raise exc
                answer=tx.text.strip()
                result={"status":"completed" if answer else "failed","result":answer,"error":"The AI provider returned an empty response after bounded recovery." if not answer else "","streamed":True,"analysis_only":True}
                self._persist_assistant_result(text, result)
                self._queue_ui("finish", result, cancel_event)
                return
            decision=self.cognitive.decide(text) if hasattr(self, "cognitive") else None
            local=decision.response if decision and decision.handled else None
            if local is not None:
                result={"status":"completed","result":local,"streamed":False,"local_memory":True,"intent":decision.intent}
                self._persist_assistant_result(text, result)
                self._queue_ui("finish", result, cancel_event)
                return
            if cancel_event.is_set(): return
            direct=self._direct_local_command(text)
            if direct is not None:
                result={"status":"completed","result":direct,"streamed":False,"direct_local":True}
                self._persist_assistant_result(text,result)
                self._queue_ui("finish", result, cancel_event)
                return
            requested_url=self.intent_router.requested_url(text)
            if requested_url:
                policy=self.agent.policy.inspect_request(text)
                if policy.get("needs_confirmation"):
                    result=self.runtime.submit(text,source="ui",require_approval=True,
                        reason="ALICE needs your confirmation before navigating to this website.")
                else:
                    result=self.runtime.submit(text,source="ui",direct_tool="browser_open",
                        direct_args={"url":requested_url})
                self._persist_assistant_result(text,result)
                self._queue_ui("finish",result,cancel_event)
                return
            requested_app=self.intent_router.requested_app(text)
            if requested_app:
                resolved=self.intent_router.resolve_app(requested_app)
                if resolved.get("status")=="exact":
                    policy=self.agent.policy.inspect_request(text)
                    if policy.get("needs_confirmation"):
                        result=self.runtime.submit(text,source="ui",require_approval=True,
                            reason="ALICE needs your confirmation before opening this application.")
                    else:
                        result=self.runtime.submit(text,source="ui",direct_tool="open_app",
                            direct_args={"command":resolved["path"]})
                    self._persist_assistant_result(text,result)
                    self._queue_ui("finish",result,cancel_event)
                    return
                if resolved.get("status")=="ambiguous":
                    names=", ".join(resolved.get("matches",[]))
                    result={"status":"completed","result":f"I found more than one app named {requested_app}: {names}. Say the exact app name to choose one.","streamed":False}
                    self._persist_assistant_result(text,result)
                    self._queue_ui("finish",result,cancel_event)
                    return
                if resolved.get("status")=="not_found":
                    suggestions=resolved.get("matches",[])
                    hint=(" Did you mean "+", ".join(suggestions)+"?") if suggestions else ""
                    result={"status":"completed","result":f"I couldn't find an installed app named {requested_app}.{hint} I haven't opened anything.","streamed":False}
                    self._persist_assistant_result(text,result)
                    self._queue_ui("finish",result,cancel_event)
                    return
            web_query=None if is_trading_request(text) else self.intent_router.web_query(text)
            if web_query:
                try:
                    result=self._perform_web_research(text,web_query,cancel_event)
                    if result is None or cancel_event.is_set(): return
                except Exception as exc:
                    result={"status":"failed","error":f"Web research failed ({type(exc).__name__}). Check your internet connection and try again.","streamed":False}
                self._persist_assistant_result(text,result)
                self._queue_ui("finish",result,cancel_event)
                return
            if self._is_self_engineering_request(text):
                sm = SelfManager(root=self.root_path, router=self.router)
                result = self._self_engineer_and_schedule(sm, text)
                self._persist_assistant_result(text, result)
                self._queue_ui("finish", result, cancel_event)
                return
            if self._is_update_request(text):
                result=self._perform_update_request(text)
                if result.get("status")=="update_ready":
                    self._persist_assistant_result(text,result)
                    self._queue_ui("update_ready", result.get("update",{}))
                    return
                self._persist_assistant_result(text,result)
                self._queue_ui("finish", result, cancel_event)
                return
            policy=self.agent.policy.inspect_request(text)
            if policy.get("needs_confirmation"):
                result=self.runtime.submit(text,source="ui",require_approval=True,reason="The request contains a consequential action. Alice will wait for your explicit approval before executing it.")
            elif self._needs_tools(text):
                result=self.runtime.submit(text,source="ui")
            else:
                tx=ResponseTransaction()
                self._queue_ui("stream_start", cancel_event)
                try:
                    for piece in self.agent.respond_text_stream(text,concise=self.concise_mode,cancel_event=cancel_event,history=self._history_prompt()):
                        if cancel_event.is_set(): return
                        tx.append(piece)
                        self._queue_ui("stream_append", cancel_event, piece)
                    state=tx.complete()
                    if not state.completed and not cancel_event.is_set():
                        fallback=self.agent.respond_text(text,concise=self.concise_mode,cancel_event=cancel_event,history=self._history_prompt()).strip()
                        if fallback:
                            tx.append(fallback); self._queue_ui("stream_append", cancel_event, fallback); state=tx.complete()
                except Exception as exc:
                    if cancel_event.is_set(): return
                    state=tx.fail(recoverable=True)
                    if state.recoverable:
                        continuation=self.agent.respond_text_recovery(text,state.text,concise=self.concise_mode,cancel_event=cancel_event,history=self._history_prompt()).strip()
                        if continuation:
                            tx.append(continuation); self._queue_ui("stream_append", cancel_event, continuation)
                            state=tx.complete()
                    if not state.completed:
                        raise exc
                answer=tx.text.strip()
                result={"status":"completed" if answer else "failed","result":answer,"error":"The AI provider returned an empty response after bounded streaming/non-stream recovery." if not answer else "","streamed":True}
        except Exception as e:
            result={"status":"failed","error":str(e),"streamed":bool(chunks) if 'chunks' in locals() else False}
        if not cancel_event.is_set():
            self._persist_assistant_result(text, result)
        self._queue_ui("finish", result, cancel_event)

    def _persist_assistant_result(self, request, result):
        """Persist the completed turn without blocking Tk's event loop."""
        try:
            if isinstance(result, dict):
                if result.get("status") == "completed":
                    display = str(result.get("result", ""))
                elif result.get("status") == "failed":
                    display = "Error: " + str(result.get("error", "Unknown error"))
                elif result.get("status") == "awaiting_approval":
                    approval = result.get("approval", {})
                    display = "I need your approval before doing this.\nReason: " + str(approval.get("reason", "Consequential action requires confirmation."))
                else:
                    display = str(result)
            else:
                display = str(result)
            if display:
                self.conversation.append("assistant", display)
                if not (isinstance(result, dict) and result.get("local_memory")):
                    self.memory.learn_outcome(request, display, self.updates.status().get("current_version") or "ALICE v4.1.0")
        except Exception:
            # Persistence failure must never take down or freeze the UI.
            pass

    def finish(self,result,cancel_event):
        if self._cancel_event is not cancel_event or cancel_event.is_set(): return
        request=getattr(self, "_last_request_text", "")
        self._cancel_event=None; self.stop_button.config(state="disabled"); self.activity.config(text=self.provider_status())
        delivery = canonicalize_response(result)
        display = delivery.text
        streamed=bool(isinstance(result,dict) and result.get("streamed"))
        if streamed:
            self._stream_end(cancel_event)
            if isinstance(result,dict) and result.get("status")!="completed":
                # A failed stream must produce a visible assistant response.
                # Previously this path only appended a terse interruption
                # marker and suppressed the canonical error shown by the
                # non-stream path, making submitted messages appear to vanish.
                self.say("Alice",display)
        else:
            self.say("Alice",display)
        if not delivery.valid:
            self.say("Alice", display)
        self.last_response=display
        if getattr(self,"_mini_mode_active",False):
            # Show a concise result in the pill, then return to the tray-only idle state.
            self._mini_transcript=(display.replace("\n", " ").strip()[:160] or "Task complete.")
            try:
                if self._mini_response_label is not None:self._mini_canvas.itemconfigure(self._mini_response_label,text=self._mini_transcript)
            except Exception:pass
            if not (self.voice.is_enabled() and ((not self.text_mode) or self._wants_voice(request))):
                self._set_orb_state("response")
        # Disk/SQLite persistence is deliberately performed by the worker thread
        # before the finish event reaches Tk. The GUI thread must remain short and
        # never wait on filesystem/database operations.
        self.root.after_idle(self._refocus_entry)
        # Explicit voice requests override Text mode for that single response.
        # Otherwise Text mode remains authoritative.
        if self.voice.is_enabled() and ((not self.text_mode) or self._wants_voice(request)):
            self.voice.speak_async(display, replace_pending=True)
            threading.Thread(target=self._voice_status_worker, daemon=True).start()


    def _voice_status_worker(self):
        try:
            s=self.voice_reliability.diagnose()
            if s.get("last_error") and not s.get("ready"):
                self._queue_ui("voice_status", str(s["last_error"])[:120])
        except Exception:
            pass

    def _apply_update_check(self, result):
        if result.get("error"):
            self.say("Alice","Update check failed: "+str(result["error"])); return
        if result.get("available"):
            self.say("Alice",f"Stable update {result.get('latest_version')} is available. Use 'Alice, update yourself' when you want me to download, verify, and prepare it.")
        elif result.get("configured"):
            self.say("Alice",f"No newer stable build is available. I am on {result.get('current_version')}.")
        else:
            self.say("Alice",result.get("message","No update source configured."))

    def _apply_voice_status(self, message):
        if not self._shutdown:
            self.activity.config(text=self.provider_status()+" • voice unavailable: "+str(message))

    def voice_dialog(self):
        self.audio_center()

    def audio_center(self):
        win=tk.Toplevel(self.root); win.title("ALICE Voice & Microphone"); win.geometry("760x560"); win.minsize(680,480); win.transient(self.root)
        nb=ttk.Notebook(win); nb.pack(fill="both",expand=True,padx=10,pady=10)
        voice_tab=tk.Frame(nb); mic_tab=tk.Frame(nb); fish_tab=tk.Frame(nb)
        nb.add(voice_tab,text="Voice output"); nb.add(mic_tab,text="Microphone input"); nb.add(fish_tab,text="Fish Audio")
        # TTS
        tk.Label(voice_tab,text="Alice voice",font=("Segoe UI",16,"bold")).pack(anchor="w",padx=16,pady=(16,4))
        tk.Label(voice_tab,text="Your selected Windows voice is stored locally and preserved across upgrades.",wraplength=680,justify="left").pack(anchor="w",padx=16,pady=4)
        # Keep the visible Windows voice picker aligned with the female-only
        # admission rule enforced by Voice.select_voice().
        all_sapi_voices=self.voice.list_voices()
        voices=[v for v in all_sapi_voices if self.voice._is_female(v)]
        labels=[f"{v['name']}  [{v['id']}]" for v in voices]
        current=self.voice.current_voice(); var=tk.StringVar(value="No TTS voices detected")
        if current:
            if current.get("mode")=="neural":var.set("Neural selected: "+current.get("name",""))
            else:var.set(next((labels[i] for i,v in enumerate(voices) if v['id']==current['id']),labels[0] if labels else "No TTS voices detected"))
        combo=ttk.Combobox(voice_tab,textvariable=var,values=labels,state="readonly",width=80); combo.pack(fill="x",padx=16,pady=12)
        vstatus=tk.Label(voice_tab,text=(f"Current: {current['name']}" if current else "No verified female Windows voice selected")+
                         f"\nWindows SAPI voices detected: {len(all_sapi_voices)}; female voices available: {len(voices)}",anchor="w"); vstatus.pack(fill="x",padx=16)
        def select_voice():
            if not voices:return
            chosen=self.voice.select_voice(voices[max(0,combo.current())]['id']); vstatus.config(text="Current: "+chosen['name'])
        def female():
            chosen=self.voice.select_female_default(); vstatus.config(text="Current: "+chosen['name'] if chosen else "No voice detected")
        row=tk.Frame(voice_tab); row.pack(pady=18)
        tk.Button(row,text="Use selected",command=select_voice,width=14).pack(side="left",padx=5)
        tk.Button(row,text="Female default",command=female,width=14).pack(side="left",padx=5)
        tk.Button(row,text="Test selected",command=lambda:self._test_selected_voice(vstatus),width=14).pack(side="left",padx=5)
        tk.Label(voice_tab,text="Microsoft neural female voices (internet required)",font=("Segoe UI",11,"bold")).pack(anchor="w",padx=16,pady=(14,3))
        neural=self.voice.female_voice_packs().get("neural",[])
        neural_labels=[f"{x['name']}  [{x['voice']}]" for x in neural]
        nvar=tk.StringVar(value="No neural voice backend")
        ncombo=ttk.Combobox(voice_tab,textvariable=nvar,values=neural_labels,state="readonly",width=80); ncombo.pack(fill="x",padx=16,pady=7)
        def select_neural():
            i=ncombo.current()
            if i<0 or i>=len(neural): return
            try:
                chosen=self.voice.select_female_neural(neural[i]['id']); vstatus.config(text="Current: "+chosen['name']+" (neural female) — ready to test")
            except Exception as exc:
                vstatus.config(text="Neural voice unavailable: "+str(exc))
        tk.Button(voice_tab,text="Use neural female",command=select_neural,width=18).pack(anchor="w",padx=16,pady=5)
        tk.Label(voice_tab,text="Offline Piper local neural voice (optional; requires your own installed Piper model)",font=("Segoe UI",11,"bold")).pack(anchor="w",padx=16,pady=(14,3))
        piper_status = self.voice.local_piper_status(refresh=True)
        piper_detail = ("Ready: configured female offline model detected" if piper_status.get("ready") else
                        "Not ready (" + str(piper_status.get("reason", "unknown")) +
                        (": " + str(piper_status.get("diagnostic")) if piper_status.get("diagnostic") else "") + "). Config: " +
                        str(piper_status.get("config_path", "")))
        tk.Label(voice_tab,text=piper_detail,wraplength=680,justify="left").pack(anchor="w",padx=16,pady=4)
        def select_piper():
            try:
                chosen=self.voice.select_local_piper()
                vstatus.config(text="Current: "+chosen["name"]+" (offline local voice)")
            except Exception as exc:
                vstatus.config(text="Offline Piper unavailable: "+str(exc))
        tk.Button(voice_tab,text="Use offline Piper voice",command=select_piper,width=22).pack(anchor="w",padx=16,pady=5)
        def test_piper_only():
            vstatus.config(text="Testing Piper synthesis and audio playback directly (no SAPI fallback)…")
            def work():
                try:
                    result = self.voice.test_local_piper_voice("Hello. I am Alice. This is a local Piper playback test.")
                except Exception as exc:
                    result = {"ok": False, "mode": "piper_local_test", "provider": "unavailable",
                              "error": str(exc), "fallback_attempted": False}
                self._queue_ui("voice_test", result)
            threading.Thread(target=work, daemon=True, name="AlicePiperOnlyTest").start()
        tk.Button(voice_tab,text="Test Piper only (no fallback)",command=test_piper_only,width=28).pack(anchor="w",padx=16,pady=5)
        # Fish Audio is an explicit cloud voice option. Its API key is saved only
        # in current-user DPAPI storage; this tab never displays or logs the key.
        tk.Label(fish_tab,text="Fish Audio voice",font=("Segoe UI",16,"bold")).pack(anchor="w",padx=16,pady=(16,4))
        tk.Label(fish_tab,text="Use the API key from your Fish Audio account and the voice/model ID of your saved voice. The key is encrypted for this Windows user and is not included in ALICE settings or upgrade packages.",wraplength=680,justify="left").pack(anchor="w",padx=16,pady=4)
        fstatus=tk.Label(fish_tab,text="",anchor="w",justify="left",wraplength=680); fstatus.pack(fill="x",padx=16,pady=8)
        tk.Label(fish_tab,text="Fish Audio API key").pack(anchor="w",padx=16)
        fkey=tk.Entry(fish_tab,show="*",width=76); fkey.pack(fill="x",padx=16,pady=(2,8))
        tk.Label(fish_tab,text="Fish Audio voice ID").pack(anchor="w",padx=16)
        fvoice=tk.StringVar(value=str(getattr(self.voice,"_fish_audio_voice_id","")))
        tk.Entry(fish_tab,textvariable=fvoice,width=76).pack(fill="x",padx=16,pady=(2,8))
        tk.Label(fish_tab,text="Saving a blank key keeps the key already stored. ‘Test voice’ sends one fixed sample sentence to Fish Audio and plays the returned audio.",wraplength=680,justify="left").pack(anchor="w",padx=16,pady=4)
        def show_fish_status(prefix=""):
            status=self.voice.fish_audio_status()
            sdk="SDK ready" if status.get("sdk_available") else "SDK dependency missing"
            state="ready" if status.get("ready") else str(status.get("reason","not configured"))
            fstatus.config(text=(prefix+"\n" if prefix else "")+f"Status: {state} • key {'saved' if status.get('key_configured') else 'not saved'} • voice ID {'saved' if status.get('voice_id_configured') else 'missing'} • {sdk}")
        def save_fish_audio_settings():
            try:
                result=self.voice.configure_fish_audio(fkey.get(),fvoice.get())
                fkey.delete(0,"end")
                show_fish_status("Fish Audio settings saved securely.")
                return result
            except Exception as exc:
                fkey.delete(0,"end")
                fstatus.config(text="Could not save Fish Audio settings: "+str(exc))
                return None
        def use_fish_audio_voice():
            if save_fish_audio_settings() is None:return
            try:
                chosen=self.voice.select_fish_audio_voice()
                vstatus.config(text="Current: Fish Audio voice "+chosen["id"])
                show_fish_status("Fish Audio voice selected. It will not fall back to another provider.")
            except Exception as exc:
                fstatus.config(text="Fish Audio voice not selected: "+str(exc))
        def test_fish_audio_voice():
            if save_fish_audio_settings() is None:return
            fstatus.config(text="Sending the fixed voice-test sentence to Fish Audio…")
            def work():
                result=self.voice.test_fish_audio_voice()
                self._queue_ui("fish_audio_test",(fstatus,result))
            threading.Thread(target=work,daemon=True,name="AliceFishAudioTest").start()
        fbuttons=tk.Frame(fish_tab); fbuttons.pack(anchor="w",padx=16,pady=12)
        tk.Button(fbuttons,text="Save settings",command=save_fish_audio_settings,width=16).pack(side="left",padx=(0,6))
        tk.Button(fbuttons,text="Use this voice",command=use_fish_audio_voice,width=16).pack(side="left",padx=6)
        tk.Button(fbuttons,text="Test voice",command=test_fish_audio_voice,width=14).pack(side="left",padx=6)
        show_fish_status()
        # Microphone
        tk.Label(mic_tab,text="Microphone input",font=("Segoe UI",16,"bold")).pack(anchor="w",padx=16,pady=(16,4))
        tk.Label(mic_tab,text="ALICE prefers a saved device, then a Bluetooth/headset microphone, then the Windows default. This avoids accidentally listening to the laptop mic.",wraplength=680,justify="left").pack(anchor="w",padx=16,pady=4)
        device_var=tk.StringVar(); devices=[]
        combo_mic=ttk.Combobox(mic_tab,textvariable=device_var,state="readonly",width=82); combo_mic.pack(fill="x",padx=16,pady=12)
        mstatus=tk.Label(mic_tab,text="",anchor="w",justify="left",wraplength=680); mstatus.pack(fill="x",padx=16,pady=5)
        def refresh_mic():
            nonlocal devices
            devices=self.microphone.list_devices(); values=[f"{d['name']}  (input {d['index']})" for d in devices]; combo_mic['values']=values
            best=self.microphone.choose_best(devices)
            if best and best in devices: combo_mic.current(devices.index(best))
            st=self.microphone.status(); chosen=(st.get('selected') or {}).get('name','none')
            mstatus.config(text=f"Selected: {chosen}\nSpeechRecognition: {'ready' if st.get('speech_recognition') else 'missing'}    Capture backend: {'ready' if st.get('sounddevice') else 'missing'}\nRecognition: {'ready' if st.get('recognition_ready') else 'blocked'} — {st.get('recognition_backend','unknown')}\nInput devices detected: {len(devices)}")
        def save_mic():
            i=combo_mic.current()
            if i<0 or i>=len(devices): return
            chosen=self.microphone.select(index=devices[i]['index']); mstatus.config(text=f"Selected and saved: {chosen['name']}")
        def test_mic():
            self.activity.config(text="Listening for a microphone test...")
            def work():
                try:
                    text=self.microphone.recognize_once(timeout=5,phrase_time_limit=5)
                    self._queue_ui("mic_test",text)
                except Exception as exc:
                    self._queue_ui("mic_test",None,str(exc))
            threading.Thread(target=work,daemon=True,name="AliceMicTest").start()
        row2=tk.Frame(mic_tab); row2.pack(pady=18)
        tk.Button(row2,text="Refresh devices",command=refresh_mic,width=14).pack(side="left",padx=5)
        tk.Button(row2,text="Use selected",command=save_mic,width=14).pack(side="left",padx=5)
        tk.Button(row2,text="Test microphone",command=test_mic,width=14).pack(side="left",padx=5)
        tk.Button(row2,text="Close",command=win.destroy,width=10).pack(side="left",padx=5)
        tk.Label(mic_tab,text="Voice input mode",font=("Segoe UI",11,"bold")).pack(anchor="w",padx=16,pady=(12,2))
        mode_var=tk.StringVar(value="Jarvis Advanced" if self.microphone.settings.get("input_mode")=="jarvis_advanced" else "ALICE local-first")
        mode_box=ttk.Combobox(mic_tab,textvariable=mode_var,values=("ALICE local-first","Jarvis Advanced"),state="readonly",width=28); mode_box.pack(anchor="w",padx=16,pady=3)
        tk.Label(mic_tab,text="Streaming sherpa shows live English words on-device. Local Whisper transcribes after you finish speaking (the current model is English-only). Google uploads audio only with your explicit consent. Translation is separate.",wraplength=680,justify="left").pack(anchor="w",padx=16,pady=3)
        recognition_labels={"Streaming sherpa (English, offline)":"sherpa_streaming","Local Whisper (offline)":"local_whisper","Google (online)":"google"}
        saved_recognition=str(self.microphone.settings.get("recognition_backend","google"))
        recognition_var=tk.StringVar(value=next((label for label,value in recognition_labels.items() if value==saved_recognition),"Google (online)"))
        ttk.Combobox(mic_tab,textvariable=recognition_var,values=tuple(recognition_labels),state="readonly",width=28).pack(anchor="w",padx=16,pady=2)
        whisper_row=tk.Frame(mic_tab); whisper_row.pack(fill="x",anchor="w",padx=16,pady=(4,2))
        tk.Label(whisper_row,text="Local Whisper model (name or converted model folder)").pack(anchor="w")
        whisper_model_var=tk.StringVar(value=str(self.microphone.settings.get("whisper_model","small.en") or "small.en"))
        whisper_path_row=tk.Frame(whisper_row); whisper_path_row.pack(fill="x",anchor="w")
        tk.Entry(whisper_path_row,textvariable=whisper_model_var,width=72).pack(side="left",fill="x",expand=True)
        def browse_whisper_model():
            selected=filedialog.askdirectory(parent=win,title="Select converted ALICE Whisper model folder")
            if selected: whisper_model_var.set(selected)
        tk.Button(whisper_path_row,text="Browse…",command=browse_whisper_model,width=10).pack(side="left",padx=(6,0))
        tk.Label(whisper_row,text="Use small.en for the default model, or browse to the converted ALICE model folder. English-only; local audio stays on this device.",wraplength=680,justify="left").pack(anchor="w",pady=(2,0))
        cloud_var=tk.BooleanVar(value=bool(self.microphone.settings.get("allow_cloud_stt",False)))
        tk.Checkbutton(mic_tab,text="I explicitly allow Google to receive microphone audio for recognition (required only for Google)",variable=cloud_var).pack(anchor="w",padx=16)
        translate_var=tk.BooleanVar(value=bool(self.microphone.settings.get("translate_enabled",False)))
        tk.Checkbutton(mic_tab,text="Translate recognized text using mtranslate (online) or Argos (offline)",variable=translate_var).pack(anchor="w",padx=16)
        translation_backend_labels={"Argos (offline; language packages required)":"argos_offline","mtranslate (online)":"mtranslate_online"}
        saved_translation=str(self.microphone.settings.get("translation_backend","argos_offline"))
        translation_backend_var=tk.StringVar(value=next((label for label,value in translation_backend_labels.items() if value==saved_translation),"Argos (offline; language packages required)"))
        ttk.Combobox(mic_tab,textvariable=translation_backend_var,values=tuple(translation_backend_labels),state="readonly",width=38).pack(anchor="w",padx=16,pady=2)
        langrow=tk.Frame(mic_tab); langrow.pack(anchor="w",padx=16,pady=2)
        tk.Label(langrow,text="Source language (auto or code)").pack(side="left")
        source_var=tk.StringVar(value=str(self.microphone.settings.get("source_language","auto")))
        tk.Entry(langrow,textvariable=source_var,width=12).pack(side="left",padx=4)
        tk.Label(langrow,text="Target language").pack(side="left",padx=(8,0))
        target_var=tk.StringVar(value=str(self.microphone.settings.get("target_language","en")))
        tk.Entry(langrow,textvariable=target_var,width=8).pack(side="left",padx=4)
        configrow=tk.Frame(mic_tab); configrow.pack(anchor="w",padx=16,pady=2)
        config_vars={}
        for label,key,default,width in (("Calibrate s","ambient_calibration_seconds","1.0",5),
                                         ("Energy ×","energy_threshold_multiplier","2.5",5),
                                         ("Min energy","minimum_energy_threshold","180",6),
                                         ("Pause s","pause_threshold","0.8",5),
                                         ("Min phrase s","phrase_threshold","0.25",5),
                                         ("Listen timeout s","listen_timeout","10",5),
                                         ("Recognition timeout s","recognition_timeout","8",5)):
            tk.Label(configrow,text=label).pack(side="left",padx=(0,2))
            var=tk.StringVar(value=str(self.microphone.settings.get(key,default))); config_vars[key]=var
            tk.Entry(configrow,textvariable=var,width=width).pack(side="left",padx=(0,7))
        jarvis_status=tk.Label(mic_tab,text="Active mode: "+mode_var.get(),anchor="w",justify="left",wraplength=680); jarvis_status.pack(fill="x",padx=16,pady=3)
        def save_input_settings():
            try:
                values={key:float(var.get()) for key,var in config_vars.items()}
                if self.jarvis_listener.running:self._stop_jarvis_listener()
                self.microphone.save_input_preferences(input_mode=("jarvis_advanced" if mode_var.get()=="Jarvis Advanced" else "alice_local_first"),
                    recognition_backend=recognition_labels[recognition_var.get()],allow_cloud_stt=bool(cloud_var.get()),translate_enabled=bool(translate_var.get()),
                    whisper_model=whisper_model_var.get().strip() or "small.en",
                    translation_backend=translation_backend_labels[translation_backend_var.get()],
                    source_language=source_var.get().strip() or "auto",target_language=target_var.get().strip() or "en",**values)
                selected_backend=recognition_labels[recognition_var.get()]
                detail={"sherpa_streaming":" • live local streaming (English)","local_whisper":" • local phrase recognition","google":" • Google audio upload explicitly enabled" if cloud_var.get() else " • Google cloud recognition disabled"}[selected_backend]
                jarvis_status.config(text="Saved input mode: "+mode_var.get()+detail)
                return True
            except Exception as exc:
                jarvis_status.config(text="Could not save input settings: "+str(exc)); return False
        row3=tk.Frame(mic_tab); row3.pack(pady=3)
        tk.Button(row3,text="Save input mode",command=save_input_settings,width=15).pack(side="left",padx=5)
        tk.Button(row3,text="Start continuous",command=lambda:(save_input_settings() and self._start_jarvis_listener()),width=16).pack(side="left",padx=5)
        tk.Button(row3,text="Stop listening",command=self._stop_jarvis_listener,width=14).pack(side="left",padx=5)
        refresh_mic()

    def _test_selected_voice(self,status_label):
        status_label.config(text="Testing selected Alice voice…"); self.activity.config(text=self.provider_status()+" • voice test running")
        def work():
            try:self._queue_ui("voice_test",self.voice.test_current_voice("Hello. I am Alice. This is my selected voice."))
            except Exception as exc:self._queue_ui("voice_test",{"ok":False,"error":str(exc),"mode":self.voice.current_mode()})
        threading.Thread(target=work,daemon=True,name="AliceVoiceTest").start()
    def _apply_voice_test(self,result):
        if result.get("ok"):
            self.activity.config(text=self.provider_status()+" • voice test passed"); self.say("Alice",f"Voice test passed: {result.get('voice','Alice')} via {result.get('provider','selected voice')}.")
        else:
            self.activity.config(text=self.provider_status()+" • voice test failed"); self.say("Alice",f"Voice test failed ({result.get('mode','unknown')}): {result.get('error') or 'selected voice produced no playable audio.'}")

    def _apply_mic_test(self, text, error=""):
        self.activity.config(text=self.provider_status())
        if error:
            self.say("Alice", "Microphone test failed: "+str(error))
        elif text:
            self.say("Alice", "I heard: "+str(text))
        else:
            self.say("Alice", "The microphone captured audio, but speech recognition could not understand it.")

    def _start_jarvis_listener(self):
        try:
            if self.microphone.settings.get("input_mode")!="jarvis_advanced":
                self._queue_ui("jarvis_status","Select and save Jarvis Advanced before starting continuous listening."); return False
            if self.jarvis_listener.start():
                self._publish_orb_state("listening")
                self._queue_ui("jarvis_status","Starting Jarvis Advanced Listening…"); return True
            if self.jarvis_listener.stopping:
                self._queue_ui("jarvis_status","The previous listening session is releasing the microphone; try Start again shortly."); return False
            self._queue_ui("jarvis_status","Jarvis Advanced Listening is already active."); return False
        except Exception as exc:
            self._queue_ui("jarvis_status",str(exc)); return False

    def _stop_jarvis_listener(self):
        stopped=self.jarvis_listener.stop(timeout=1.0)
        self._publish_orb_state("idle")
        self._queue_ui("jarvis_status","Jarvis listener stopped; microphone released." if stopped else "Stopping after the current bounded recognition request…")
        return stopped

    def _handle_jarvis_transcript(self,text,translated=None):
        if self._shutdown:return
        chosen=str(translated or text or "").strip()
        if not chosen:return
        if translated:self.activity.config(text="Translated recognized speech; sending the translated text to ALICE.")
        self.entry.delete(0,"end"); self.entry.insert(0,chosen); self._sync_message_to_native(); self.send()

    def show_approvals(self):
        pending=self.runtime.approvals.pending()
        if not pending:self.say("Alice","There are no pending approvals.");return
        for a in pending:
            ok=messagebox.askyesno("Alice approval",f"Approve this action?\n\n{a['action']}\n\n{a['reason']}")
            self.runtime.approvals.resolve(a['id'],ok)
            if ok:
                result=self.runtime.submit(a['action'],source="approved-ui"); self.say("Alice",str(result))

    def listen(self):
        if self.microphone.settings.get("input_mode")=="jarvis_advanced":
            if self.jarvis_listener.running:self._stop_jarvis_listener()
            else:self._start_jarvis_listener()
            return
        self._publish_orb_state("listening")
        self.activity.config(text="Listening... (microphone input)")
        def work():
            try:
                text=self.microphone.recognize_once(timeout=5,phrase_time_limit=12)
                self._queue_ui("heard",text)
            except Exception as exc:
                self._queue_ui("heard_error",str(exc))
        threading.Thread(target=work,daemon=True,name="AliceSTT").start()
    def _heard(self,text):
        # Voice callbacks may arrive on a worker thread. Never touch Tk here.
        self._queue_ui("heard", text)

    def _handle_heard_error(self,error):
        self._publish_orb_state("idle")
        self.activity.config(text=self.provider_status())
        self.say("Alice", "I could not start microphone listening: "+str(error))

    def _handle_heard(self,text):
        self.activity.config(text=self.provider_status())
        if text:
            self._mini_transcript=str(text)[:140]
            if getattr(self,"_orb_canvas",None) is not None:self._orb_canvas.itemconfigure(self._mini_transcript_id,text=self._mini_transcript)
            self.entry.delete(0,"end"); self.entry.insert(0,text); self._sync_message_to_native(); self.send()
        else:
            self._publish_orb_state("idle")
            self.say("Alice","I couldn't understand the microphone input. Open Tools → Voice & Microphone to verify the selected input device and run a test.")
    def eyes(self):
        r=screenshot();self.say("Alice","I captured my current screen." if r.get("ok") else "I couldn't capture the screen: "+str(r))
    def run(self):
        """Run the classic native interface as a safe fallback."""
        try:self.root.mainloop()
        finally:
            try:self.runtime.stop_scheduler()
            except Exception:pass
            try:self.root.destroy()
            except Exception:pass

def _close_premium_runtime(holder):
    """Quit the hidden Tk runtime after the premium WebView window closes."""
    close_event=holder.get("close_event")
    if close_event is not None:
        try:close_event.set()
        except Exception:pass
    app=holder.get("app")
    if app is None or getattr(app,"_premium_window_closed",False):return
    app._premium_window_closed=True
    app._shutdown=True
    # When the WebView callback is on another thread, let Tk's own loop poll
    # the event instead of calling Tkinter cross-thread and leaving mainloop alive.
    if close_event is None:
        try:app.root.after(0,app.root.quit)
        except Exception:pass


def _run_premium_ui(webview):
    """Run the bundled HTML UI in WebView2 and keep Tk on its owning thread."""
    from .premium_bridge import PremiumUIBridge
    page=Path(__file__).resolve().parent / "assets" / "alice-premium-ui.html"
    if not page.is_file():raise RuntimeError("Bundled premium interface is missing")
    bridge=PremiumUIBridge()
    holder={"app":None,"close_event":threading.Event()}
    start_hidden=os.getenv("ALICE_START_HIDDEN","0").lower() in {"1","true","yes","on"}
    window=webview.create_window(
        f"Alice — ALICE Elysium {AliceUI._app_version()}", page.as_uri(), width=1440, height=960,
        min_size=(980,680), background_color="#070a13", js_api=bridge, hidden=start_hidden,
    )
    def run_tk_runtime():
        app=AliceUI()
        holder["app"]=app
        bridge.bind(app)
        app._publish_premium_event("runtime_ready",{"status":"ready"})
        app._publish_premium_event("conversation_ready",{"status":"ready"})
        app._premium_window=window
        app._premium_visible=not start_hidden
        app.root.withdraw()
        def stop_when_webview_closes():
            if holder["close_event"].is_set():
                try:app.root.quit()
                except Exception:pass
                return
            try:app.root.after(50,stop_when_webview_closes)
            except Exception:pass
        app.root.after(50,stop_when_webview_closes)
        try:app.root.mainloop()
        finally:
            try:app.runtime.stop_scheduler()
            except Exception:pass
            try:app.root.destroy()
            except Exception:pass
    def close_runtime():
        _close_premium_runtime(holder)
    # Closing the WebView must also stop its hidden Tk runtime.
    try:window.events.closed += close_runtime
    except Exception:pass
    webview.start(func=run_tk_runtime, gui="edgechromium")
    close_runtime()

def main():
    try:
        import webview
        _run_premium_ui(webview)
    except Exception:
        # Keep ALICE usable when the Windows WebView2 host cannot start.
        AliceUI().run()
if __name__=="__main__":main()



