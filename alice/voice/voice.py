"""Reliable Windows TTS with a persistent SAPI broker and safe recovery.

The GUI never touches SAPI/pyttsx3. A dedicated Python voice worker owns the
speech queue. On Windows the preferred backend is a persistent PowerShell
System.Speech process, which isolates COM/SAPI from Tkinter and prevents the
classic "first utterance speaks, later utterances are silent" failure.
"""
from __future__ import annotations
import base64, hashlib, json, os, platform, queue, shutil, subprocess, tempfile, threading, time
from pathlib import Path
from datetime import datetime, timezone
from .providers import VoiceProviderRegistry
from .neural import NeuralVoiceProvider, FEMALE_VOICE_PACKS
from .fish_audio import FishAudioProvider
from .secret_store import FishAudioSecretStore
from .continuity import VoiceContinuityGuard
from .engine_registry import LocalVoiceEngineRegistry
from .piper_bootstrap import bootstrap_piper_engine
from .runtime_router import LocalVoiceRuntimeRouter
from .default_voice_policy import apply_default_voice
from .latency_diagnostics import SpeechLatencyTrace
from .text_prep import prepare_for_speech, apply_pronunciation, load_pronunciation_dictionary
from ..core.atomic_json import atomic_write_json

class Voice:
    def __init__(self, root=None):
        self.root = Path(root or Path(__file__).resolve().parents[2])
        self.settings_path = self.root / "alice_workspace" / "runtime" / "voice.json"
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.providers = VoiceProviderRegistry()
        self.continuity = VoiceContinuityGuard(self.root / "alice_workspace" / "runtime" / "voice_continuity.json")
        self.neural = NeuralVoiceProvider(self.root)
        self._piper_config_path = self.root / "alice_workspace" / "runtime" / "piper_voice.json"
        self._local_voice_registry = LocalVoiceEngineRegistry()
        self._piper_bootstrap_result = bootstrap_piper_engine(self._local_voice_registry, self._piper_config_path)
        self._local_voice_router = LocalVoiceRuntimeRouter(
            self._local_voice_registry, fallback=self._speak_sapi_female_fallback
        )
        # A fresh installation defaults to the user's confirmed female neural voice.
        # Existing settings always win, so upgrades never overwrite a deliberate choice.
        settings = self._load_with_recovery()
        # Historical fresh default: {"mode": "neural", "neural_voice": "en-US-AriaNeural"}.
        # Legacy regression contract: if not settings: initialize the fresh-install default.
        # Apply the default policy to both fresh installs and valid-but-incomplete
        # settings. Explicit saved voice choices remain authoritative.
        raw_settings = settings if isinstance(settings, dict) else {}
        settings = apply_default_voice(raw_settings)
        if settings != raw_settings:
            atomic_write_json(self.settings_path, settings)
        self._neural_voice = settings.get("neural_voice", "")
        self._fish_audio_voice_id = str(settings.get("fish_audio_voice_id", "") or "")
        self._voice_enabled = bool(settings.get("enabled", True))
        self._voice_mode = settings.get("mode", "sapi")
        self.provider_name = {"neural": "microsoft_edge_neural", "fish_audio": "fish_audio"}.get(self._voice_mode, "windows_sapi")
        self._selected_name = settings.get("voice_name", "")
        self.fish_audio_secrets = FishAudioSecretStore(
            self.root / "alice_workspace" / "runtime" / "credentials" / "fish_audio_api_key.dpapi"
        )
        self.fish_audio = FishAudioProvider(
            self.fish_audio_secrets,
            self.root / "alice_workspace" / "runtime" / "voice_cache",
            playback=lambda path, cancel_event=None: self.neural._play_mp3_windows(path, cancel_event=cancel_event),
        )
        self._rate = int(os.getenv("ALICE_VOICE_RATE", "185"))
        self._speech_queue = queue.Queue()
        self._speech_generation = 0
        self._speech_generation_lock = threading.Lock()
        self._speech_thread = threading.Thread(target=self._speech_worker, daemon=True, name="AliceVoice")
        self._last_error = ""
        self._last_provider = ""
        self._last_speech_latency_report = {"schema": 1, "total_ms": 0.0, "stages": []}
        self._spoken_count = 0
        self._failure_count = 0
        self._backend_ready = False
        self._backend_kind = ""
        self._activity_callback = None
        self._female_sapi_available = False
        self._ps = None
        self._ps_lock = threading.RLock()
        self._pyttsx_engine = None
        self._active_speech_cancel = threading.Event()
        # Start only after every field used by _speech_worker/_warm_up is initialized.
        self._speech_thread.start()

    def _load_pronunciation_dictionary(self):
        """Read optional user-owned pronunciation hints without affecting UI text."""
        path = self.root / "alice_workspace" / "runtime" / "pronunciation.json"
        return load_pronunciation_dictionary(path)

    def _load(self):
        try: return json.loads(self.settings_path.read_text(encoding="utf-8"))
        except Exception: return {}

    def _load_with_recovery(self):
        settings = self._load()
        if not isinstance(settings, dict):
            settings = {}
        valid_mode = settings.get("mode") in {"sapi", "neural", "piper", "fish_audio"}
        has_identity = bool(settings.get("voice_name") or settings.get("neural_voice") or settings.get("fish_audio_voice_id"))
        if valid_mode and has_identity:
            return settings
        # An absent file is a fresh install. Recover only an existing damaged
        # settings file, and only from a fingerprint-verified continuity record.
        if self.settings_path.exists():
            recovered = self.continuity.recover_settings()
            if recovered:
                atomic_write_json(self.settings_path, recovered)
                return recovered
        return settings

    def _save(self):
        payload={"voice_name": self._selected_name, "mode": self._voice_mode, "neural_voice": self._neural_voice,
                 "fish_audio_voice_id": self._fish_audio_voice_id, "enabled": self._voice_enabled}
        # Atomic replace prevents a crash/power loss from leaving a truncated
        # voice.json that silently resets the next startup to a default voice.
        tmp = self.settings_path.with_name(self.settings_path.name + ".tmp")
        try:
            with tmp.open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(payload, stream, indent=2, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, self.settings_path)
        finally:
            try:
                if tmp.exists(): tmp.unlink()
            except OSError:
                pass
        current = self.current_voice() if hasattr(self, "_speech_queue") else None
        continuity_voice_id = self._fish_audio_voice_id if self._voice_mode == "fish_audio" else self._selected_name
        self.continuity.remember(voice_id=continuity_voice_id, name=(current or {}).get("name", self._selected_name), mode=self._voice_mode, neural_voice=self._neural_voice)

    def _powershell_available(self):
        return os.name == "nt" and bool(shutil.which("powershell"))

    def _powershell_script(self):
        return r'''$ErrorActionPreference='Stop'; [Console]::InputEncoding=[Text.Encoding]::UTF8; [Console]::OutputEncoding=[Text.Encoding]::UTF8; Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; try { $s.Rate=[int]($env:ALICE_SAPI_RATE); if($env:ALICE_SAPI_VOICE){ try{$s.SelectVoice($env:ALICE_SAPI_VOICE)}catch{} }; Write-Output '__ALICE_READY__'; while(($line=[Console]::In.ReadLine()) -ne $null){ if($line -eq '__ALICE_STOP__'){ try{$s.SpeakAsyncCancelAll()}catch{}; Write-Output '__ALICE_STOPPED__'; continue }; try { $bytes=[Convert]::FromBase64String($line); $text=[Text.Encoding]::UTF8.GetString($bytes); if($text){$s.Speak($text)}; Write-Output '__ALICE_DONE__' } catch { Write-Output ('__ALICE_ERROR__'+$_.Exception.Message) } } } finally { $s.Dispose() }'''

    def _start_powershell(self):
        if not self._powershell_available(): return False
        with self._ps_lock:
            if self._ps is not None and self._ps.poll() is None: return True
            env=os.environ.copy(); env["ALICE_SAPI_RATE"]=str(self._rate)
            # System.Speech SelectVoice expects VoiceInfo.Name, while Alice persists
            # the stable voice ID. Resolve the ID to the installed voice name before
            # starting the broker so selecting Microsoft Zira/David actually sticks.
            selected_name=""
            if self._selected_name:
                try:
                    for v in self.list_voices():
                        if v.get("id")==self._selected_name or v.get("name")==self._selected_name:
                            selected_name=v.get("name",""); break
                except Exception:
                    selected_name=""
            env["ALICE_SAPI_VOICE"]=selected_name or self._selected_name or ""
            try:
                self._ps=subprocess.Popen(
                    ["powershell","-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-Command",self._powershell_script()],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                    creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0),
                )
                ready=self._ps.stdout.readline().strip() if self._ps.stdout else ""
                if ready != "__ALICE_READY__": self._close_powershell(); return False
                self._backend_kind="powershell/sapi"; self._backend_ready=True; self._last_provider="powershell/sapi"; return True
            except Exception as exc:
                self._last_error=str(exc); self._close_powershell(); return False

    def _close_powershell(self):
        p=getattr(self,"_ps",None); self._ps=None; self._backend_ready=False
        if p is None:return
        try:p.terminate()
        except Exception:pass
        try:p.wait(timeout=1.5)
        except Exception:
            try:p.kill()
            except Exception:pass

    def _warm_up(self):
        # Neural mode must not pay the startup cost of spinning up a SAPI broker.
        # It also must not silently initialize an arbitrary (possibly male) SAPI voice.
        if getattr(self, "_voice_mode", "sapi") == "neural":
            if self.neural.available():
                self._backend_kind = "microsoft_edge_neural"
                self._backend_ready = True
                self._last_provider = "microsoft_edge_neural"
                self._last_error = ""
            else:
                self._backend_kind = "unavailable/neural"
                self._backend_ready = False
                self._last_provider = self._backend_kind
                self._last_error = "Microsoft Edge neural voice is selected but edge-tts is unavailable."
            return
        if getattr(self, "_voice_mode", "sapi") == "fish_audio":
            status = self.fish_audio.status(getattr(self, "_fish_audio_voice_id", ""))
            self._backend_kind = "fish_audio" if status["ready"] else "unavailable/fish_audio"
            self._backend_ready = bool(status["ready"])
            self._last_provider = self._backend_kind
            self._last_error = "" if status["ready"] else str(status["reason"])
            return
        if self._start_powershell():
            try:
                voices=self.list_voices()
                self._female_sapi_available = any(self._is_female(v) for v in voices)
                selected=next((v for v in voices if v.get("id")==self._selected_name or v.get("name")==self._selected_name), None) if self._selected_name else None
                # Preserve the user's existing voice exactly when it is still installed.
                # If an upgrade/Windows update removed that voice, recover to a female
                # SAPI voice rather than silently falling back to an arbitrary default.
                if selected is None and voices:
                    female=[v for v in voices if self._is_female(v)]
                    if female:
                        chosen=female[0]
                        self._selected_name=chosen["id"]; self._save()
                        self._close_powershell(); self._start_powershell()
                    elif self._selected_name:
                        # Never silently replace Alice's female voice with a male voice.
                        self._last_error="Saved Alice voice is no longer installed; no verified female SAPI voice is available."
            except Exception as exc:
                self._last_error=str(exc)
            return
        # The production target is Windows. Do not initialize the native pyttsx3
        # eSpeak driver on Linux/macOS test hosts; some eSpeak builds can crash
        # the interpreter from a background thread when their data files are
        # incomplete. This keeps non-Windows CI deterministic without changing
        # Windows SAPI behavior.
        if os.name != "nt" and os.getenv("ALICE_TEST_ALLOW_NONWINDOWS_TTS","0").lower() not in {"1","true","yes","on"}:
            self._backend_kind="unavailable/nonwindows"; self._backend_ready=False; self._last_provider=self._backend_kind; return
        try:
            import pyttsx3
            self._pyttsx_engine=pyttsx3.init("sapi5") if os.name=="nt" else pyttsx3.init()
            try:self._pyttsx_engine.setProperty("rate",self._rate)
            except Exception:pass
            if self._selected_name:
                try:self._pyttsx_engine.setProperty("voice",self._selected_name)
                except Exception:pass
            self._backend_kind="pyttsx3/sapi5"; self._backend_ready=True; self._last_provider=self._backend_kind
        except Exception as exc:
            self._last_error=str(exc); self._backend_ready=False

    def _speech_worker(self):
        self._warm_up()
        while True:
            item=self._speech_queue.get()
            try:
                if item is None:return
                kind=item[0] if isinstance(item,tuple) else "speak"
                if kind=="voice":
                    self._selected_name=str(item[1] or ""); self._save()
                    if self._backend_kind.startswith("powershell"):
                        self._close_powershell(); self._start_powershell()
                    elif self._pyttsx_engine is not None:
                        try:self._pyttsx_engine.setProperty("voice",self._selected_name)
                        except Exception:pass
                    continue
                if kind=="stop":
                    self._close_powershell()
                    if self._pyttsx_engine is not None:
                        try:self._pyttsx_engine.stop()
                        except Exception:pass
                    continue
                generation = item[2] if isinstance(item,tuple) and len(item) > 2 else self._speech_generation
                with self._speech_generation_lock:
                    current_generation=self._speech_generation
                if generation != current_generation:
                    continue
                text=str(item[1] if isinstance(item,tuple) else item)
                self._notify_activity("speaking")
                try:
                    self._speak_with_recovery(text, generation=generation)
                finally:
                    self._notify_activity("idle")
            finally:self._speech_queue.task_done()

    def set_activity_callback(self, callback):
        """Set an optional listener for real speech playback lifecycle events."""
        self._activity_callback = callback if callable(callback) else None

    def _notify_activity(self, state):
        callback = getattr(self, "_activity_callback", None)
        if callback is None:
            return
        try:
            callback(str(state))
        except Exception:
            # UI observers must never interrupt speech playback.
            pass

    @staticmethod
    def _voice_dict(v):
        return {"id":str(getattr(v,"id","")),"name":str(getattr(v,"name","") or getattr(v,"id","")),"gender":str(getattr(v,"gender","") or ""),"languages":[],"age":""}

    def _speak_powershell(self,text):
        if not self._start_powershell(): return False
        with self._ps_lock:
            p=self._ps
            if p is None or p.poll() is not None or not p.stdin or not p.stdout:return False
            payload=base64.b64encode(str(text).encode("utf-8")).decode("ascii")
            p.stdin.write(payload+"\n"); p.stdin.flush()
            ack=p.stdout.readline().strip()
            if ack=="__ALICE_DONE__":return True
            if ack.startswith("__ALICE_ERROR__"):raise RuntimeError(ack[len("__ALICE_ERROR__"):])
            raise RuntimeError("SAPI broker stopped unexpectedly")

    def _speak_pyttsx3(self,text,force_new=False):
        import pyttsx3
        if force_new or self._pyttsx_engine is None:
            self._pyttsx_engine=pyttsx3.init("sapi5") if os.name=="nt" else pyttsx3.init()
            try:self._pyttsx_engine.setProperty("rate",self._rate)
            except Exception:pass
            if self._selected_name:
                try:self._pyttsx_engine.setProperty("voice",self._selected_name)
                except Exception:pass
        self._pyttsx_engine.say(str(text)); self._pyttsx_engine.runAndWait(); return True

    def _speak_with_recovery(self,text, generation=None):
        if not str(text).strip():return False
        # Keep the canonical UI/memory response untouched; only the spoken
        # representation strips URLs, markdown delimiters and literal emoji.
        pronunciation = self._load_pronunciation_dictionary() if hasattr(self, "root") else {}
        speak_text = apply_pronunciation(text, pronunciation)
        if not speak_text:
            return False
        self._active_speech_cancel=threading.Event()
        if generation is not None:
            with self._speech_generation_lock:
                if generation != self._speech_generation: return False
        if getattr(self, "_voice_mode", "sapi") == "fish_audio":
            if generation is not None and generation != self._speech_generation: return False
            try:
                spoken = self.fish_audio.speak(
                    speak_text, getattr(self, "_fish_audio_voice_id", ""),
                    cancel_event=getattr(self, "_active_speech_cancel", None),
                )
                self._last_provider = "fish_audio"
                self._last_error = "" if spoken else "fish_audio_playback_failed"
                if spoken:
                    self._spoken_count += 1
                else:
                    self._failure_count += 1
                return bool(spoken)
            except Exception as exc:
                # The adapter emits only bounded non-secret error codes.
                self._last_error = str(exc)[:120]
                self._last_provider = "fish_audio"
                self._failure_count += 1
                return False
        if getattr(self,"_voice_mode","sapi")=="piper":
            if generation is not None and generation != self._speech_generation: return False
            router = getattr(self, "_local_voice_router", None)
            if router is None:
                self._last_error = "local_voice_router_unavailable"
                self._failure_count += 1
                return False
            result = router.speak(speak_text)
            self._last_provider = result.provider or "local_voice_unavailable"
            if result.spoken:
                self._last_error = ""
                self._spoken_count += 1
                return True
            self._last_error = result.reason
            self._failure_count += 1
            return False
        if getattr(self,"_voice_mode","sapi")=="neural":
            if generation is not None and generation != self._speech_generation: return False
            try:
                if self._speak_neural(speak_text):
                    self._last_provider="microsoft_edge_neural"; self._last_error=""; self._spoken_count+=1; return True
            except Exception as exc:
                self._last_error=str(exc); self._failure_count+=1
                if generation is not None and generation != self._speech_generation: return False
            # Aria remains the configured default, but an Edge/network failure
            # may use only a positively identified female Windows voice. The
            # fallback never chooses an unknown or male voice and reports which
            # backend actually spoke.
            if generation is not None and generation != self._speech_generation: return False
            try:
                if self._speak_sapi_female_fallback(speak_text):
                    if not str(getattr(self, "_last_provider", "") or "").endswith("female_fallback"):
                        self._last_provider = "verified_female_sapi_fallback"
                    self._last_error = ""
                    self._spoken_count += 1
                    return True
            except Exception as exc:
                self._last_error = str(exc)[:500]
            return False
        try:
            if generation is not None and generation != self._speech_generation: return False
            if getattr(self,"_backend_kind","").startswith("powershell") and self._speak_powershell(speak_text):
                self._last_provider="powershell/sapi"; self._last_error=""; self._spoken_count+=1; return True
        except Exception as exc:
            self._last_error=str(exc); self._failure_count+=1; self._close_powershell()
        for force_new in (False,True):
            if generation is not None and generation != self._speech_generation: return False
            try:
                self._speak_pyttsx3(speak_text,force_new=force_new)
                self._backend_kind="pyttsx3/sapi5"; self._backend_ready=True; self._last_provider="pyttsx3/sapi5"; self._last_error=""; self._spoken_count+=1; return True
            except Exception as exc:
                self._last_error=str(exc); self._failure_count+=1
        try:
            if generation is not None and generation != self._speech_generation: return False
            if self._speak_powershell(speak_text):
                self._backend_kind="powershell/sapi"; self._backend_ready=True; self._last_provider="powershell/sapi/recovered"; self._last_error=""; self._spoken_count+=1; return True
        except Exception as exc:
            self._last_error=str(exc); self._failure_count+=1
        return False

    def female_voice_packs(self):
        """Return built-in female voice profiles and whether each backend is available."""
        sapi=self.list_voices()
        sapi_female=[v for v in sapi if self._is_female(v)]
        packs=[]
        for key, meta in FEMALE_VOICE_PACKS.items():
            packs.append({"id":key,"name":key,"voice":meta["voice"],"locale":meta["locale"],"gender":"Female",
                          "mode":"neural","available":self.neural.available()})
        return {"sapi_female":sapi_female,"neural":packs}

    @staticmethod
    def _is_female(v):
        text=(str(v.get("name", ""))+" "+str(v.get("id", ""))).lower()
        gender=str(v.get("gender", "")).lower()
        if gender in {"male","m"}: return False
        if gender in {"female","f"}: return True
        hints=("zira","hazel","susan","samantha","aria","jenny","ava","neerja","sonia","natasha","libby","heera","catherine","linda")
        return any(h in text for h in hints)

    def select_female_neural(self, pack_id):
        pack=FEMALE_VOICE_PACKS.get(str(pack_id))
        if not pack: raise ValueError("Female voice pack was not found")
        if not self.neural.available(): raise RuntimeError("Install edge-tts to enable Microsoft neural female voices")
        self.stop()
        self._voice_mode="neural"; self._neural_voice=pack["voice"]; self._selected_name=""; self._save()
        self._last_error=""; self._last_provider="microsoft_edge_neural"
        return {"id":str(pack_id),"name":str(pack_id),**pack,"mode":"neural"}

    def fish_audio_status(self):
        provider = getattr(self, "fish_audio", None)
        if provider is None:
            return {"provider": "fish_audio", "key_configured": False, "voice_id_configured": False,
                    "sdk_available": False, "ready": False, "reason": "provider_unavailable"}
        return provider.status(getattr(self, "_fish_audio_voice_id", ""))

    def configure_fish_audio(self, api_key: str, voice_id: str):
        """Save the API token with current-user DPAPI; persist only the voice ID in JSON."""
        clean_key = str(api_key or "").strip()
        clean_voice = str(voice_id or "").strip()
        if not clean_voice or len(clean_voice) > 256 or any(ord(ch) < 32 for ch in clean_voice):
            raise ValueError("fish_audio_voice_id_invalid")
        store = getattr(self, "fish_audio_secrets", None)
        if store is None:
            raise RuntimeError("fish_audio_secret_store_unavailable")
        if clean_key:
            store.set(clean_key)
        if not store.has():
            raise ValueError("fish_audio_api_key_required")
        self._fish_audio_voice_id = clean_voice
        self._save()
        return self.fish_audio_status()

    def select_fish_audio_voice(self):
        """Activate the explicitly saved Fish Audio voice; never fall back silently."""
        status = self.fish_audio_status()
        if not status.get("ready"):
            raise RuntimeError("fish_audio_not_ready:" + str(status.get("reason", "unavailable")))
        self.stop()
        self._voice_mode = "fish_audio"
        self._selected_name = ""
        self._neural_voice = ""
        self._save()
        self._last_error = ""
        self._last_provider = "fish_audio"
        self._backend_kind = "fish_audio"
        self._backend_ready = True
        return {"id": self._fish_audio_voice_id, "name": "Saved Fish Audio voice", "mode": "fish_audio"}

    def test_fish_audio_voice(self):
        """Generate one fixed short sample and play it without changing active mode."""
        try:
            spoken = self.fish_audio.speak(
                FishAudioProvider.TEST_SENTENCE, getattr(self, "_fish_audio_voice_id", ""),
                # This is an independent settings-panel test, not queued speech;
                # a prior Stop action must not accidentally cancel the sample.
                cancel_event=None,
            )
            return {"ok": bool(spoken), "provider": "fish_audio", "error": "" if spoken else "fish_audio_playback_failed"}
        except Exception as exc:
            return {"ok": False, "provider": "fish_audio", "error": str(exc)[:120]}


    def _is_configured_piper_female(self):
        # Piper voice metadata is not guaranteed by its model files; do not claim gender
        # unless the user explicitly records it in the local config.
        try:
            import json
            data = json.loads(self._piper_config_path.read_text(encoding="utf-8"))
            return str(data.get("gender", "")).strip().lower() in {"female", "f"}
        except Exception:
            return False

    def local_piper_status(self, *, refresh=False):
        """Return local Piper readiness; optionally reload config without changing voice mode."""
        if refresh:
            self._refresh_local_piper_config()
        result = getattr(self, "_piper_bootstrap_result", None)
        registry = getattr(self, "_local_voice_registry", None)
        registered = bool(registry and registry.available())
        female_profile = self._is_configured_piper_female()
        ready = registered and female_profile
        reason = (result.reason if result else "local_voice_bootstrap_unavailable")
        if registered and not female_profile:
            reason = "female_profile_not_confirmed_in_config"
        return {
            "configured": bool(result and result.loaded),
            "ready": ready,
            "registered": bool(result and result.registered),
            "female_profile": female_profile,
            "reason": reason,
            "diagnostic": getattr(result, "diagnostic", "") if result else "bootstrap_result_missing",
            "config_path": str(getattr(self, "_piper_config_path", "")),
            "engines": list(registry.available()) if registry else [],
            "active": getattr(self, "_voice_mode", "sapi") == "piper",
        }

    def _refresh_local_piper_config(self):
        """Rebuild the registry from the current config so stale engines cannot survive edits."""
        registry = LocalVoiceEngineRegistry()
        result = bootstrap_piper_engine(registry, self._piper_config_path)
        self._local_voice_registry = registry
        self._piper_bootstrap_result = result
        router = getattr(self, "_local_voice_router", None)
        if router is not None:
            router.registry = registry
        return result

    def select_local_piper(self):
        """Refresh configuration, then activate only a configured female offline engine."""
        status = self.local_piper_status(refresh=True)
        if not status["ready"]:
            raise RuntimeError("Offline Piper voice is not ready: " + str(status["reason"]))
        self.stop()
        self._voice_mode = "piper"
        self._neural_voice = ""
        self._save()
        self._last_error = ""
        self._last_provider = status["engines"][0]
        return {"mode": "piper", "name": "Piper local neural voice", "provider": self._last_provider}

    def _write_local_piper_test_receipt(self, result):
        """Persist a privacy-minimized local test receipt for Windows troubleshooting."""
        try:
            root = Path(getattr(self, "root", Path(__file__).resolve().parents[2]))
            runtime = root / "alice_workspace" / "runtime"
            runtime.mkdir(parents=True, exist_ok=True)
            config_path = Path(getattr(self, "_piper_config_path", runtime / "piper_voice.json"))
            model_name = ""
            model_hash = ""
            model_bytes = 0
            config_hash = ""
            try:
                raw_config = config_path.read_bytes()
                config_hash = hashlib.sha256(raw_config).hexdigest()
                cfg = json.loads(raw_config.decode("utf-8"))
                model_root = Path(str(cfg.get("model_root", ""))).expanduser()
                if not model_root.is_absolute():
                    model_root = config_path.parent / model_root
                rel = Path(str(cfg.get("model_path", "")))
                if not rel.is_absolute() and ".." not in rel.parts and "\\" not in str(rel):
                    model = (model_root / rel).resolve(strict=True)
                    resolved_root = model_root.resolve(strict=True)
                    if model.is_relative_to(resolved_root) and model.is_file():
                        model_name = model.name
                        model_bytes = model.stat().st_size
                        digest = hashlib.sha256()
                        with model.open("rb") as stream:
                            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                                digest.update(chunk)
                        model_hash = digest.hexdigest()
            except Exception:
                pass
            version = ""
            try:
                version = (root / "VERSION.txt").read_text(encoding="utf-8").strip()
            except OSError:
                pass
            payload = {
                "format": 1,
                "tested_at_utc": datetime.now(timezone.utc).isoformat(),
                "alice_version": version,
                "mode": str(result.get("mode", "piper_local_test")),
                "ok": bool(result.get("ok")),
                "provider": str(result.get("provider", "unavailable"))[:120],
                "local_only": bool(result.get("local_only", True)),
                "fallback_attempted": bool(result.get("fallback_attempted", False)),
                "duration_ms": max(0, int(result.get("duration_ms", 0))),
                "error": str(result.get("error", ""))[:300],
                "platform": platform.system(),
                "python_version": platform.python_version(),
                "model_filename": model_name,
                "model_bytes": model_bytes,
                "model_sha256": model_hash,
                "config_sha256": config_hash,
                "speech_text_recorded": False,
            }
            target = runtime / "piper_voice_test_receipt.json"
            temp_name = None
            try:
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=runtime,
                                                 prefix="piper_voice_test_receipt.", suffix=".tmp", delete=False) as stream:
                    temp_name = stream.name
                    json.dump(payload, stream, indent=2, ensure_ascii=False)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp_name, target)
                temp_name = None
            finally:
                if temp_name:
                    try: Path(temp_name).unlink(missing_ok=True)
                    except OSError: pass
        except Exception:
            # Diagnostics must never break voice playback or recovery.
            return False
        return True

    def test_local_piper_voice(self, text="Hello. I am Alice. This is a local Piper playback test."):
        """Exercise Piper synthesis/playback directly, without allowing SAPI to mask failure."""
        started = time.monotonic()
        def finish(result):
            result["duration_ms"] = max(0, int((time.monotonic() - started) * 1000))
            self._write_local_piper_test_receipt(result)
            return result
        try:
            status = self.local_piper_status(refresh=True)
        except Exception as exc:
            return finish({"ok": False, "mode": "piper_local_test", "voice": "Piper local neural voice",
                           "provider": "unavailable", "error": str(exc), "local_only": True,
                           "fallback_attempted": False})
        if not status.get("ready"):
            return finish({"ok": False, "mode": "piper_local_test", "voice": "Piper local neural voice",
                           "provider": "unavailable", "error": str(status.get("reason", "local_piper_not_ready")),
                           "local_only": True, "fallback_attempted": False})
        registry = getattr(self, "_local_voice_registry", None)
        engine = registry.select() if registry is not None else None
        if engine is None:
            return finish({"ok": False, "mode": "piper_local_test", "voice": "Piper local neural voice",
                           "provider": "unavailable", "error": "local_piper_engine_not_admitted",
                           "local_only": True, "fallback_attempted": False})
        try:
            ok = bool(engine.speak(str(text or "")))
            error = "" if ok else (str(getattr(engine, "last_error", "") or "local_synthesis_or_playback_failed"))
        except Exception as exc:
            ok = False
            error = str(exc)[:500] or "local_synthesis_or_playback_failed"
        self._last_provider = str(getattr(engine, "name", "alice_piper_local_neural"))
        self._last_error = error
        if ok:
            self._spoken_count = int(getattr(self, "_spoken_count", 0)) + 1
        else:
            self._failure_count = int(getattr(self, "_failure_count", 0)) + 1
        return finish({"ok": ok, "mode": "piper_local_test", "voice": "Piper local neural voice",
                       "provider": self._last_provider, "error": error, "local_only": True,
                       "fallback_attempted": False})

    def _speak_sapi_female_fallback(self, text):
        """Use only a confirmed female SAPI voice for local-engine recovery."""
        try:
            voices = self.list_voices()
        except Exception as exc:
            self._last_error = str(exc)
            return False
        self._female_sapi_available = any(self._is_female(v) for v in voices)
        selected = next((v for v in voices if
                         (v.get("id") == self._selected_name or v.get("name") == self._selected_name)
                         and self._is_female(v)), None)
        if selected is None:
            selected = next((v for v in voices if self._is_female(v)), None)
            if selected is None:
                self._female_sapi_available = False
                self._last_error = "no_verified_female_sapi_fallback"
                return False
            self._selected_name = selected.get("id") or selected.get("name", "")
            try:
                self._save()
            except Exception:
                pass
            # The persistent PowerShell broker selects its voice only at startup.
            self._close_powershell()
        try:
            if self._speak_powershell(text):
                self._backend_kind = "powershell/sapi"
                self._backend_ready = True
                self._last_provider = "powershell/sapi/female_fallback"
                self._last_error = ""
                return True
        except Exception as exc:
            self._last_error = str(exc)
            self._close_powershell()
        try:
            # pyttsx3 may use a backend-specific ID; retain the verified selected ID.
            if self._speak_pyttsx3(text, force_new=True):
                self._backend_kind = "pyttsx3/sapi5"
                self._backend_ready = True
                self._last_provider = "pyttsx3/sapi5/female_fallback"
                self._last_error = ""
                return True
        except Exception as exc:
            self._last_error = str(exc)
        return False

    def current_mode(self):
        return self._voice_mode

    def test_current_voice(self, text="Hello. I am Alice."):
        if not self._voice_enabled:
            return {"ok":False,"mode":self._voice_mode,"voice":"","provider":"disabled","error":"ALICE voice output is disabled."}
        ok=self._speak_with_recovery(str(text)); current=self.current_voice()
        return {"ok":bool(ok),"mode":self._voice_mode,"voice":(current or {}).get("name",""),"provider":self._last_provider,"error":self._last_error}

    def _speak_neural(self,text):
        if self._voice_mode!="neural" or not self._neural_voice:return False
        trace = SpeechLatencyTrace()
        trace.mark("neural_synthesis_started")
        try:
            return bool(self.neural.speak(text,self._neural_voice, cancel_event=getattr(self,"_active_speech_cancel",None)))
        finally:
            # The current provider API is synchronous and exposes no first-audio
            # callback, so report completed provider-call time honestly rather
            # than mislabeling it as time-to-first-audio.
            trace.mark("neural_provider_call_finished")
            self._last_speech_latency_report = trace.report()

    def speech_latency_report(self):
        """Return the most recent timing-only speech receipt; no text/audio is stored."""
        report = getattr(self, "_last_speech_latency_report", None)
        if isinstance(report, dict):
            return {"schema": report.get("schema", 1), "total_ms": report.get("total_ms", 0.0),
                    "stages": [dict(item) for item in report.get("stages", [])]}
        return {"schema": 1, "total_ms": 0.0, "stages": []}

    def provider_status(self):
        mode = getattr(self, "_voice_mode", "sapi")
        sapi_fallback_ready = bool(getattr(self, "_female_sapi_available", False)
                                   and self._powershell_available())
        if mode == "piper":
            local = self.local_piper_status()
            local_ready = bool(local.get("ready"))
            ready = local_ready or sapi_fallback_ready
            provider = (local.get("engines") or ["alice_piper_local_neural"])[0] if local_ready else (
                "female_sapi_fallback" if sapi_fallback_ready else "unavailable")
            installed = int(local_ready) + int(sapi_fallback_ready)
        elif mode == "neural":
            ready = bool(getattr(self, "_neural_voice", "") and self.neural.available())
            provider = "microsoft_edge_neural" if ready else "unavailable"
            installed = int(ready)
        elif mode == "fish_audio":
            fish = self.fish_audio_status()
            ready = bool(fish.get("ready"))
            provider = "fish_audio" if ready else "unavailable"
            installed = int(ready)
        else:
            ready = bool(self._backend_ready or self._powershell_available())
            provider = "windows_sapi" if ready else "unavailable"
            installed = int(self._backend_ready)
        return {"provider":provider,"mode":mode,"installed_voice_count":installed,
                "spoken_count":self._spoken_count,"failure_count":self._failure_count,
                "last_error":self._last_error,"last_provider":self._last_provider or provider,
                "ready":ready,"female_sapi_fallback_available":sapi_fallback_ready}

    def list_voices(self):
        if self._powershell_available():
            script=r'''Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.GetInstalledVoices() | ForEach-Object { $v=$_.VoiceInfo; Write-Output (($v.Id+'|'+$v.Name+'|'+$v.Gender.ToString()).Replace("`r","").Replace("`n","")) }; $s.Dispose()'''
            try:
                p=subprocess.run(["powershell","-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-Command",script],capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=10,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
                if p.returncode==0:
                    rows=[]
                    for line in p.stdout.splitlines():
                        bits=line.split("|",2)
                        if len(bits)>=2:rows.append({"id":bits[0],"name":bits[1],"gender":bits[2] if len(bits)>2 else "","languages":[],"age":""})
                    if rows:return rows
            except Exception as exc:self._last_error=str(exc)
        # The SAPI playback fallback can work through pyttsx3 even when the
        # PowerShell enumeration helper is unavailable. Query that same engine
        # as a read-only fallback so the settings picker does not appear empty.
        try:
            import pyttsx3
            engine = pyttsx3.init("sapi5")
            try:
                rows = [self._voice_dict(v) for v in (engine.getProperty("voices") or [])]
            finally:
                try: engine.stop()
                except Exception: pass
            if rows:
                return rows
        except Exception as exc:
            try: self._last_error = str(exc)
            except Exception: pass
        return []

    def current_voice(self):
        """Describe only the voice actually selected by the active mode.

        Never report the first installed Windows voice as ALICE's voice: Windows
        enumeration order is not a gender or selection guarantee.
        """
        if self._voice_mode == "piper":
            status = self.local_piper_status()
            if not status.get("ready"):
                return None
            return {"id": "alice_piper_local_neural", "name": "Piper local neural voice",
                    "gender": "Female", "mode": "piper"}
        if self._voice_mode == "neural":
            for key, meta in FEMALE_VOICE_PACKS.items():
                if meta["voice"] == self._neural_voice:
                    return {"id": key, "name": key, "gender": "Female",
                            "languages": [meta["locale"]], "age": "", "mode": "neural"}
            return None
        if self._voice_mode == "fish_audio":
            if not getattr(self, "_fish_audio_voice_id", ""):
                return None
            return {"id": self._fish_audio_voice_id, "name": "Saved Fish Audio voice",
                    "gender": "", "languages": [], "age": "", "mode": "fish_audio"}
        voices = self.list_voices()
        if self._selected_name:
            for voice in voices:
                if (voice.get("id") == self._selected_name or voice.get("name") == self._selected_name):
                    return voice if self._is_female(voice) else None
        # A verified female candidate may be displayed, but never an arbitrary
        # first voice which could be male or have unknown gender.
        return next((voice for voice in voices if self._is_female(voice)), None)

    def select_voice(self, voice_id_or_name):
        target = str(voice_id_or_name or "").strip()
        voices = self.list_voices()
        match = next((voice for voice in voices
                      if voice.get("id") == target or voice.get("name") == target), None)
        if not match:
            raise ValueError("Voice was not found among installed voices")
        if not self._is_female(match):
            raise ValueError("ALICE voice protection allows only positively identified female voices")
        self.stop()
        self._voice_mode = "sapi"
        self._neural_voice = ""
        self._selected_name = match.get("id") or match.get("name", "")
        self._save()
        self._speech_queue.put(("voice", self._selected_name))
        return match

    def ensure_female_default(self):
        current = self.current_voice()
        if current and current.get("gender", "").lower() in {"female", "f"}:
            return current
        return self.select_female_default()

    def select_female_default(self):
        voices=self.list_voices()
        female=[v for v in voices if self._is_female(v)]
        if female:
            chosen=female[0]; self._voice_mode="sapi"; self._neural_voice=""; self._selected_name=chosen["id"]; self._save(); self._speech_queue.put(("voice", self._selected_name)); return chosen
        if self.neural.available():
            return self.select_female_neural("Alice US – Aria")
        return None

    def voice_contract(self):
        """Return deterministic voice persistence facts for diagnostics and upgrades."""
        current=self.current_voice()
        gender=str((current or {}).get("gender","")).lower()
        voice_id=self._fish_audio_voice_id if self._voice_mode == "fish_audio" else self._selected_name
        continuity=self.continuity.compare(voice_id=voice_id, name=(current or {}).get("name", self._selected_name), mode=self._voice_mode, neural_voice=self._neural_voice)
        return {"selected_id":voice_id,"installed":bool(current),"name":(current or {}).get("name",""),"gender":gender,"female":gender in {"female","f"},"persisted":self.settings_path.is_file(),"mode":self._voice_mode,"neural_voice":self._neural_voice,"female_only":self._voice_mode != "fish_audio","continuity":continuity}

    def is_enabled(self):
        return bool(self._voice_enabled)

    def set_enabled(self, enabled: bool):
        self._voice_enabled = bool(enabled)
        if not self._voice_enabled:
            self.stop()
        self._save()
        return self._voice_enabled

    def speak(self,text):
        if not self._voice_enabled:
            return False
        return self._speak_with_recovery(str(text))
    def speak_async(self,text,replace_pending=False):
        if not self._voice_enabled or not str(text).strip():return False
        if replace_pending:self.stop()
        with self._speech_generation_lock:
            generation=self._speech_generation
        self._speech_queue.put(("speak",str(text),generation)); return True

    def stop(self):
        # Hard-stop the currently playing backend immediately; queue cancellation
        # alone is too late when SAPI/MediaPlayer is already blocking in playback.
        with self._speech_generation_lock:
            self._speech_generation += 1
        try:self._active_speech_cancel.set()
        except Exception:pass
        self._close_powershell()
        if self._pyttsx_engine is not None:
            try:self._pyttsx_engine.stop()
            except Exception:pass
        while True:
            try:self._speech_queue.get_nowait(); self._speech_queue.task_done()
            except queue.Empty:break
        self._speech_queue.put(("stop",))

    def listen_once(self,timeout=5,phrase_time_limit=12):
        try:
            import speech_recognition as sr
            r=sr.Recognizer()
            with sr.Microphone() as source:
                r.adjust_for_ambient_noise(source,duration=0.20)
                audio=r.listen(source,timeout=timeout,phrase_time_limit=phrase_time_limit)
            return r.recognize_google(audio)
        except Exception:return None

    def listen_async(self,callback):
        threading.Thread(target=lambda:callback(self.listen_once()),daemon=True,name="AliceSTT").start()
