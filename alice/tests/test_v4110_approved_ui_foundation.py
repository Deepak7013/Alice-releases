from collections import Counter
from pathlib import Path
import re
from types import SimpleNamespace

from alice.ui.premium_bridge import PremiumUIBridge


def _ui_html():
    return (Path(__file__).parents[1] / "ui" / "assets" / "alice-premium-ui.html").read_text(encoding="utf-8")


def _approved_ui_css():
    return (Path(__file__).parents[1] / "ui" / "assets" / "alice-native-orbital-ui.css").read_text(encoding="utf-8")


def test_approved_theme_tokens_and_reusable_crystal_surface_exist():
    html = _ui_html()
    css = _approved_ui_css()

    assert "--font-ui:" in html
    assert "--font-display:" in html
    assert "--font-mono:" in html
    assert ".crystal-panel{" in html
    assert "--alice-cyan: #53e1e6" in css
    assert "rgba(62,211,222,.11)" in html
    assert "DYNAMIC FIELD" not in html
    assert "60 FPS TARGET" not in html


def test_workspace_and_immersive_theme_choice_persists_locally():
    html = _ui_html()

    assert 'id="themeSwitch"' in html
    assert 'body[data-theme="immersive"]' in html
    assert "localStorage.getItem('alice.ui.theme')" in html
    assert "localStorage.setItem('alice.ui.theme'" in html
    assert "Switch to Workspace theme" in html


def test_bottom_voice_console_uses_existing_speech_input_and_reports_state():
    html = _ui_html()

    assert 'id="voiceBtn"' in html
    assert 'class="tool-btn voice-action" id="voiceBtn"' in html
    assert html.count('id="voiceConsoleMic"') == 1
    assert "const voiceConsoleMic=$('#voiceConsoleMic')" in html
    assert "setVoiceConsole(true,'LISTENING · SPEAK NOW')" in html
    assert "MICROPHONE LISTENING" in html


def test_radial_feature_launcher_routes_to_existing_workspace_views():
    html = _ui_html()

    assert 'id="orbitalNav"' in html
    assert 'aria-controls="orbitalNav"' in html
    assert "label:'Conversation',glyph:'◌',view:'Conversation'" in html
    assert "label:'Memory',glyph:'◇',view:'Memory'" in html
    assert "label:'ALICE tools',glyph:'✦',view:'Tools'" in html
    assert "label:'Voice and microphone',glyph:'♫',view:'Voice'" in html
    assert 'document.querySelector(`[data-view="${node.dataset.orbitView}"]`)' in html


def test_radial_views_open_as_real_panels_while_the_orb_remains_visible():
    html = _ui_html()
    css = _approved_ui_css()

    assert 'id="closeOrbitPanel"' in html
    assert "document.body.classList.add('orbital-panel-mode','orbital-panel-opening')" in html
    assert "function revealOrbitPanel()" in html
    assert "animation:orbitPanelOpen" in css
    assert "prefers-reduced-motion: reduce" in css
    assert "document.body.classList.remove('orbital-panel-mode','orbit-panel-returning','orbital-panel-opening')" in html
    assert "event.key==='Escape'" in html
    assert "body.orbital-panel-mode .core-card" in css
    assert "body.orbital-panel-mode .chat-drawer.open" in css
    assert "body.orbital-panel-mode .task-workspace:not([hidden])" in css
    assert "Return to orb" in html
    assert 'url("alice-orb-background.png")' not in css


def test_capability_map_has_review_first_entries_for_actual_alice_domains():
    html = _ui_html()
    css = _approved_ui_css()

    assert 'id="capabilitiesWorkspace"' in html
    assert "$('#capabilitiesWorkspace').hidden=!isCapabilities" in html
    for domain in ("Reasoning &amp; planning", "Web research", "Files &amp; workspace",
                   "Desktop &amp; apps", "Memory &amp; context", "Voice &amp; microphone",
                   "Trading research", "Devices &amp; integrations", "Local brain", "Automations"):
        assert domain in html
    assert "[data-capability-prompt]" in html
    assert "function revealOrbitPanel()" in html
    assert "Do not place live trades" in html
    assert "capability-card:focus-visible" in css


def test_system_health_particle_opens_live_metrics_and_recovery_is_separate():
    html = _ui_html()
    assert 'id="systemHealthWorkspace"' in html
    assert 'data-health-mirror="cpu"' in html
    assert 'data-health-mirror="ram"' in html
    assert 'id="systemHealthWorkspaceRefresh"' in html
    assert "refreshSystemHealth();refreshBrainReadiness()" in html
    assert "mirrorHealth('storage'" in html
    assert 'data-view="Recovery"' in html
    assert "{label:'Recovery monitor',glyph:'⟲',view:'Recovery'}" in html
    assert "isRecovery=v==='Recovery'" in html
    assert "$('#recoveryWorkspace').hidden=!isRecovery;if(isRecovery)refreshRecovery()" in html


def test_feature_panels_support_persistent_move_resize_minimize_and_dock():
    html = _ui_html()
    css = _approved_ui_css()

    assert "alice.ui.orbit-panel-layout.v1" in html
    assert "function activeOrbitPanel()" in html
    assert "function setOrbitPanelFloating(panel,rect)" in html
    assert "function saveOrbitPanelLayout(panel)" in html
    assert "toolbar.dataset.orbitDragHandle=''" in html
    assert "is-orbit-minimized" in html
    assert "Dock feature panel beside the orb" in html
    assert "Alt plus arrow keys" in html
    assert "resize:both!important" in css
    assert ".is-orbit-minimized > :not(.orbit-panel-toolbar)" in css
    assert "--orbit-panel-width" in html


def test_runtime_status_does_not_claim_connected_while_starting_or_offline():
    html = _ui_html()

    assert "ALICE RUNTIME CONNECTED" in html
    assert "ALICE STARTING" in html
    assert "RUNTIME OFFLINE" in html
    assert "OFFLINE · ALICE RUNTIME" in html


def test_settings_exposes_appearance_voice_and_local_brain_controls():
    html = _ui_html()

    assert 'id="providerTitle">ALICE Settings' in html
    assert 'id="themeSelect"' in html
    assert 'id="settingsVoice"' in html
    assert 'id="openBrainSetup"' in html
    assert "api.open_native_panel('voice')" in html


def test_task_manager_view_uses_read_only_local_task_history():
    html = _ui_html()

    assert 'data-view="TaskManager"' in html
    assert 'id="taskWorkspace"' in html
    assert "api.list_tasks(30)" in html
    assert "does not resume, rerun, or delete tasks" in html


def test_task_history_bridge_caps_results_and_omits_storage_paths():
    class Tasks:
        def __init__(self):
            self.requested_limit = None

        def list_tasks(self, limit):
            self.requested_limit = limit
            return [{
                "id": "12345678",
                "status": "completed",
                "request": "Open the project",
                "result": "Verified",
                "started": 1,
                "finished": 2,
                "path": "should not escape",
            }]

    manager = Tasks()
    result = PremiumUIBridge(SimpleNamespace(tasks=manager)).list_tasks(500)

    assert manager.requested_limit == 50
    assert result["ok"] is True
    assert result["tasks"] == [{
        "id": "12345678",
        "status": "completed",
        "request": "Open the project",
        "result": "Verified",
        "started": 1.0,
        "finished": 2.0,
    }]


def test_browser_files_and_apps_panels_prepare_reviewable_requests():
    html = _ui_html()

    for view in ("Browser", "Files", "Apps"):
        assert f'data-view="{view}"' in html
        assert f'data-workspace-action="{view}"' in html
    assert "Request prepared. Review it and send when you’re ready." in html
    assert "Do not move, overwrite, or delete files" in html
    assert "Do not launch or close anything until I approve" in html
    assert "workspaceActions.hidden=!isAction" in html
    assert "['Browser','Files','Apps'].includes(v)" in html


def test_notifications_center_only_displays_received_runtime_events():
    html = _ui_html()

    assert 'id="notificationDialog"' in html
    assert 'id="notificationFeed"' in html
    assert "recordNotification(item,ev)" in html
    assert "They are not stored as permanent desktop notifications." in html


def test_brain_center_reports_live_local_readiness_and_opens_setup():
    html = _ui_html()

    assert 'data-view="BrainCenter"' in html
    assert 'id="brainWorkspace"' in html
    assert "api.get_brain_status()" in html
    assert 'id="brainSetupDialog"' in html
    assert "openBrainSetup()" in html
    assert "api.save_gemini_settings" in html
    assert "model_available" in html
    assert "Gemini is ALICE’s primary reasoning provider" in html
    assert "Primary reasoning" in html
    assert "Gemini is primary · setup required" in html
    assert "No hosted AI account or API key is used for local reasoning" not in html


def test_automations_view_reads_local_scheduler_and_routes_edits_to_native_manager():
    html = _ui_html()

    assert 'id="automationWorkspace"' in html
    assert "api.list_automations()" in html
    assert "This view is read-only" in html
    assert "Automations:'goals'" in html
    assert "Review schedules here; open Goals & Tasks to make changes." in html


def test_premium_bridge_exposes_primary_provider_and_optional_local_model_without_secrets(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    class Router:
        local_fast_model = "gemma3:270m"
        gemini_model = "gemini-3.8-flash"
        runtime_policy = SimpleNamespace(mode="gemini_primary")

        def available(self):
            return {"gemini": False}

        def local_status(self):
            return {"installed": True, "reachable": True, "model": "llama3.2:latest",
                    "model_available": True, "models": ["llama3.2:latest", "gemma3:270m"],
                    "base_url": "http://127.0.0.1:11434", "error": "private detail"}

    result = PremiumUIBridge(SimpleNamespace(router=Router())).get_brain_status()

    assert result == {"ok": True, "primary_provider": "gemini",
                      "primary_model": "gemini-3.8-flash", "gemini_configured": False,
                      "gemini_connection": "setup_required", "ollama_installed": True,
                      "provider_configured": False,
                      "reachable": True,
                      "model": "llama3.2:latest", "model_available": True,
                      "quick_model": "gemma3:270m", "quick_model_available": True,
                      "installed_models": ["llama3.2:latest", "gemma3:270m"],
                      "api_key_required": True}
    assert "base_url" not in result and "error" not in result


def test_premium_bridge_lists_schedule_metadata_without_revealing_prompts():
    class Scheduler:
        def list(self):
            return [{"id": "abc123", "name": "Weekly report", "interval_seconds": 3600,
                     "enabled": True, "next_run": 10, "last_run": 5,
                     "request": "private task prompt", "token": "secret"}]

    result = PremiumUIBridge(SimpleNamespace(runtime=SimpleNamespace(scheduler=Scheduler()))).list_automations()

    assert result == {"ok": True, "automations": [{"id": "abc123", "name": "Weekly report",
                      "interval_seconds": 3600, "enabled": True, "next_run": 10.0, "last_run": 5.0}]}
    assert "private task prompt" not in repr(result) and "secret" not in repr(result)


def test_brain_center_exposes_five_connected_screens_and_focus_controls():
    html = _ui_html()

    for screen in ("overview", "memory", "learning", "retrieval", "reasoning"):
        assert f'data-brain-screen="{screen}"' in html
    assert "api.get_learning_status()" in html
    assert "api.search_knowledge(query,12)" in html
    assert "api.get_reasoning_activity(25)" in html
    assert 'id="focusModeBtn"' in html
    assert 'id="miniModeBtn"' in html
    assert "localStorage.setItem('alice.ui.focus'" in html
    assert "localStorage.setItem('alice.ui.density'" in html


def test_learning_bridge_returns_only_aggregate_counters():
    class Learning:
        def stats(self):
            return {"experience_records": 4, "successful": 3, "failed": 1,
                    "lessons": 2, "private_prompt": "must not escape"}

    result = PremiumUIBridge(SimpleNamespace(learning=Learning())).get_learning_status()

    assert result == {"ok": True, "counters": {
        "experience_records": 4, "successful": 3, "failed": 1, "lessons": 2,
        "promoted": 0, "eval_cases": 0, "regression_seeds": 0,
        "verified_recoveries": 0, "regressions": 0}}
    assert "private_prompt" not in repr(result)


def test_knowledge_bridge_strips_credentials_and_query_from_source_url():
    class Acquirer:
        def search(self, query, limit):
            return [{"id": "abc", "topic": "topic", "text": "snippet",
                     "source": {"kind": "url", "title": "source",
                                "locator": "https://user:pass@example.com/page?token=secret#part"},
                     "confidence": .8, "trusted": True}]

    result = PremiumUIBridge(SimpleNamespace(knowledge_acquirer=Acquirer())).search_knowledge("topic")

    assert result["ok"] is True
    assert result["items"][0]["source_url"] == "https://example.com/page"
    assert "pass" not in repr(result) and "secret" not in repr(result)


def test_reasoning_activity_bridge_omits_raw_audit_payloads():
    class Audit:
        def recent(self, limit):
            return [{"event": "task_returned", "time": "now",
                     "data": {"request": "private prompt", "state": "verified",
                              "verified": True, "path": "C:/private"}}]

    result = PremiumUIBridge(SimpleNamespace(runtime=SimpleNamespace(audit=Audit()))).get_reasoning_activity()

    assert result == {"ok": True, "items": [{"title": "Task finished", "state": "verified",
                                               "verified": True, "time": "now"}]}
    assert "private prompt" not in repr(result) and "C:/private" not in repr(result)


def test_minimize_to_mini_queues_the_existing_companion_behavior():
    class App:
        def __init__(self):
            self.event = None

        def _queue_ui(self, event, payload):
            self.event = (event, payload)

    app = App()
    result = PremiumUIBridge(app).minimize_to_mini()

    assert result["ok"] is True
    assert app.event == ("premium_minimize_to_mini", None)


def test_conversation_shortcuts_route_to_existing_task_memory_and_activity_views():
    html = _ui_html()

    assert 'id="conversationTabChat"' in html
    assert "$('#conversationTabTasks').addEventListener('click',()=>document.querySelector('[data-view=\"TaskManager\"]').click())" in html
    assert "$('#conversationTabMemory').addEventListener('click',()=>document.querySelector('[data-view=\"Memory\"]').click())" in html
    assert "$('#conversationTabActivity').addEventListener('click',()=>$('#notificationsBtn').click())" in html


def test_recovery_monitor_uses_sanitized_read_only_lifecycle_records():
    html = _ui_html()

    assert 'id="recoveryWorkspace"' in html
    assert "api.get_reasoning_activity(30)" in html
    assert "Raw prompts and audit payloads stay private." in html
    assert "Open Task Manager" in html


def test_orbital_launcher_exposes_real_alice_surfaces_and_drafts_extra_capabilities_safely():
    html = _ui_html()

    for feature in (
        "Conversation", "Web browser", "Research with sources", "Files", "Apps control",
        "Brain Center", "Memory", "Learning Center", "Knowledge retrieval", "Reasoning activity",
        "Task Manager", "Workflow Library", "Recovery monitor", "System health", "Voice and microphone",
        "Capabilities and skills", "Android device control", "Hardware controls",
        "Camera and visual understanding", "Self-engineering", "Repository review",
        "Local AI setup", "Integrations and connected devices", "Conversation history", "Trading research",
        "Notifications and activity", "Settings and themes", "Mini ALICE companion",
    ):
        assert f"label:'{feature}'" in html
    assert 'aria-label="Orbital feature navigation"' in html
    assert "orbitNav.inert=!open" in html
    assert "Request drafted in chat. Review it before sending." in html
    assert "api.open_native_panel(node.dataset.orbitPanel)" in html
    assert "actions={notifications:()=>$('#notificationsBtn').click(),settings:()=>$('#settingsBtn').click(),mini:()=>$('#miniModeBtn').click()}" in html
    assert "const radiusX=Math.max(72,Math.min(rect.width*.40,rect.width/2-24)),radiusY=Math.max(60,Math.min(rect.height*.27,rect.height/2-24))" in html
    assert "@container (max-width:600px){.orbital-node{width:28px;height:28px;font-size:12px}}" in html
    assert "const fallbackSamples=Array.from({length:513}" in html
    assert "const perimeter=fallbackLengths[fallbackLengths.length-1]" in html
    assert "const target=perimeter*orbitalPhase;let low=0,high=fallbackLengths.length-1" in html
    assert "const orbitalPhase=i/nodes.length" in html
    assert "node.style.setProperty('--orbit-delay',`${-86*orbitalPhase}s`)" in html
    assert '@keyframes featureOrbit{from{offset-distance:0%}to{offset-distance:100%}}' in html


def test_premium_ui_ids_remain_unique():
    ids = re.findall(r'\bid="([^"]+)"', _ui_html())
    assert [name for name, count in Counter(ids).items() if count > 1] == []


def test_workspace_panels_can_move_resize_and_restore_saved_layout():
    html = _ui_html()
    css = _approved_ui_css()

    assert "alice.ui.panel-layout.v1" in html
    assert "function savePanelLayout(panel)" in html
    assert "setPanelFloating(panel,rect)" in html
    assert "head.addEventListener('pointerdown'" in html
    assert "head.addEventListener('keydown'" in html
    assert "panelResizeObserver=new ResizeObserver" in html
    assert 'data-panel-minimize="systemHealthPanel"' in html
    assert 'data-panel-close="notesRailPanel"' in html
    assert 'data-panel-restore="systemHealthPanel"' in html
    assert ".panel.is-floating" in css
    assert "resize:both" in css


def test_approved_workspace_rail_uses_home_chat_and_hides_unapproved_footer_cards():
    html = _ui_html()
    css = _approved_ui_css()

    assert 'data-view="Overview"' in html and '<span>Home</span></button>' in html
    assert 'data-view="Conversation"' in html and '<span>Chat</span></button>' in html
    assert '.sidebar .access-card,' in css
    assert '.sidebar .profile { display:none!important; }' in css
    assert '.sidebar .nav-btn[data-view="Capabilities"]' in css
    assert '.sidebar .nav-btn#navSettings { order:9; }' in css


def test_voice_first_composer_starts_collapsed_and_supports_double_tap_text_entry():
    html = _ui_html()
    css = _approved_ui_css()

    assert '.composer:not(.expanded) #promptInput' in css
    assert "$('#expandTextInput').addEventListener('click'" in html
    assert "voiceButton.addEventListener('dblclick'" in html
    assert "form.classList.add('expanded')" in html


def test_workflow_studio_has_library_builder_and_truthful_run_monitor():
    html = _ui_html()
    css = _approved_ui_css()

    for element_id in (
        "workflowLibraryView", "workflowBuilderView", "workflowMonitorView",
        "workflowLibraryList", "workflowStepList", "workflowAddStep",
        "workflowSaveDraft", "workflowPrepareReview", "workflowTaskMonitorList",
        "workflowScheduleMonitorList", "workflowApproval", "workflowVerify",
        "workflowRecovery", "workflowPermission",
    ):
        assert f'id="{element_id}"' in html
    for tab in ("library", "builder", "monitor"):
        assert f'data-workflow-tab="{tab}"' in html
    assert "alice.ui.workflow-drafts.v1" in html
    assert "local-draft" in html
    assert "No schedule is activated and no native action runs from this draft editor." in html
    assert "This draft is not registered with ALICE" in html
    assert ".workflow-step" in css
    assert ".workflow-builder-layout" in css
    assert "prefers-reduced-motion:reduce" in css or "prefers-reduced-motion: reduce" in css


def test_workflow_studio_drafts_require_name_and_step_and_prepare_review_without_sending():
    html = _ui_html()
    assert "Give this workflow a name before saving." in html
    assert "Add at least one step before saving this workflow." in html
    assert "function prepareWorkflowReview(draft)" in html
    assert "toast('Workflow review request prepared in chat. It has not been sent.')" in html
    assert "do not execute or activate anything" in html
    assert "function refreshWorkflowMonitor()" in html
    assert "api.list_tasks(20)" in html
    assert "api.list_automations()" in html


def test_approved_neural_globe_has_shaded_shell_and_spherical_reference_lines():
    html = _ui_html()

    assert "const globeR=base*.84*pulse" in html
    assert "const globeFill=ctx.createRadialGradient" in html
    assert "const terminator=ctx.createLinearGradient" in html
    assert "for(let lat=-3;lat<=3;lat++)" in html
    assert "for(let mer=-3;mer<=3;mer++)" in html
    assert "Atmospheric edge" in html
    assert "base=Math.min(w*.255,h*.315,185)" in html
