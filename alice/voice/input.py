"""Robust microphone discovery and speech capture for ALICE.

The module keeps audio-device selection separate from TTS. It prefers the
Windows-visible input device selected by ALICE, then a matching Bluetooth /
headset device, then the OS default. SoundDevice is used when available so
ALICE does not depend on PyAudio's native build; SpeechRecognition remains the
recognition adapter.
"""
from __future__ import annotations
import json, os, threading
from contextlib import contextmanager
from pathlib import Path
from ..core.atomic_json import atomic_write_json

class MicrophoneManager:
    def __init__(self, root=None):
        self.root=Path(root or Path(__file__).resolve().parents[2]).resolve()
        self.path=self.root/'alice_workspace'/'runtime'/'audio_input.json'
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self._lock=threading.RLock()
        self._capture_lock=threading.Lock()
        self.settings=self._load()

    def _load(self):
        try:
            data=json.loads(self.path.read_text(encoding='utf-8'))
            return data if isinstance(data,dict) else {}
        except Exception:
            return {}

    def _save(self):
        atomic_write_json(self.path, self.settings)

    def save_input_preferences(self, **values):
        """Persist only the supported input-mode preferences; never alter TTS."""
        allowed={"input_mode", "allow_cloud_stt", "recognition_backend", "whisper_model", "streaming_model_dir",
                 "translate_enabled", "translation_backend", "source_language",
                 "target_language", "ambient_calibration_seconds", "energy_threshold_multiplier",
                 "minimum_energy_threshold", "pause_threshold", "phrase_threshold",
                 "listen_timeout", "recognition_timeout"}
        with self._lock:
            for key, value in values.items():
                if key not in allowed:
                    raise ValueError(f"Unsupported microphone preference: {key}")
                self.settings[key]=value
            self.settings["updated_at"]=__import__('time').time()
            self._save()

    @contextmanager
    def capture_session(self):
        """Guarantee one ALICE capture path owns the microphone at a time."""
        lock=getattr(self,"_capture_lock",None)
        if lock is None:  # Keep small test doubles and older constructed instances compatible.
            lock=threading.Lock(); self._capture_lock=lock
        if not lock.acquire(blocking=False):
            raise RuntimeError("The microphone is already in use by another ALICE listening mode.")
        try:
            yield
        finally:
            lock.release()

    @staticmethod
    def _normalize_name(name):
        return ' '.join(str(name or '').lower().split())

    def list_devices(self):
        devices=[]
        # sounddevice is the primary backend because it is easier to deploy on
        # modern Windows/Python than PyAudio. Import is optional for diagnostics.
        try:
            import sounddevice as sd
            for idx,info in enumerate(sd.query_devices()):
                if int(info.get('max_input_channels',0))>0:
                    devices.append({
                        'index':idx,
                        'name':str(info.get('name','')),
                        'hostapi':str(info.get('hostapi','')),
                        'max_input_channels':int(info.get('max_input_channels',0)),
                        'default_samplerate':float(info.get('default_samplerate',16000) or 16000),
                    })
            default=None
            try: default=int(sd.default.device[0])
            except Exception: default=None
        except Exception as exc:
            default=None
            # PyAudio remains a fallback for machines where it is already installed.
            try:
                import pyaudio
                pa=pyaudio.PyAudio()
                for idx in range(pa.get_device_count()):
                    info=pa.get_device_info_by_index(idx)
                    if int(info.get('maxInputChannels',0))>0:
                        devices.append({'index':idx,'name':str(info.get('name','')),
                                        'hostapi':str(info.get('hostApi',info.get('hostapi',''))),
                                        'max_input_channels':int(info.get('maxInputChannels',0)),
                                        'default_samplerate':float(info.get('defaultSampleRate',16000) or 16000)})
                try: default=int(pa.get_default_input_device_info().get('index'))
                except Exception: default=None
                pa.terminate()
            except Exception:
                self.settings['last_device_error']=str(exc)
        # de-duplicate devices returned by unusual host-api configurations
        unique=[]; seen=set()
        for d in devices:
            key=(d.get('index'),d.get('name'))
            if key not in seen:
                seen.add(key); unique.append(d)
        selected=self.settings.get('device_name','')
        selected_index=self.settings.get('device_index')
        for d in unique:
            d['selected']=bool((selected and self._normalize_name(d['name'])==self._normalize_name(selected)) or (selected_index is not None and d['index']==selected_index))
            d['default']=bool(default is not None and d['index']==default)
        return unique

    def choose_best(self, devices=None):
        devices=devices if devices is not None else self.list_devices()
        if not devices:return None
        saved_name=self._normalize_name(self.settings.get('device_name',''))
        saved_index=self.settings.get('device_index')
        if saved_name:
            exact=next((d for d in devices if self._normalize_name(d['name'])==saved_name),None)
            if exact:return exact
        if saved_index is not None:
            exact=next((d for d in devices if d['index']==saved_index),None)
            if exact:return exact
        # Prefer Bluetooth/headset/earbud microphones when present. This fixes the
        # common laptop-mic-vs-headset ambiguity without hard-coding one brand.
        keywords=('bluetooth','headset','headphones','earbuds','buds','airpods','hands-free','wireless')
        preferred=[d for d in devices if any(k in self._normalize_name(d['name']) for k in keywords)]
        if preferred:return preferred[0]
        return next((d for d in devices if d.get('default')),devices[0])

    def select(self, index=None, name=None):
        devices=self.list_devices()
        chosen=None
        if name is not None:
            target=self._normalize_name(name)
            chosen=next((d for d in devices if self._normalize_name(d['name'])==target),None)
            if chosen is None:
                chosen=next((d for d in devices if target and target in self._normalize_name(d['name'])),None)
        elif index is not None:
            chosen=next((d for d in devices if int(d['index'])==int(index)),None)
        if chosen is None: raise ValueError('Microphone device was not found')
        with self._lock:
            self.settings['device_index']=chosen['index']; self.settings['device_name']=chosen['name']; self.settings['updated_at']=__import__('time').time(); self._save()
        return chosen

    def status(self):
        devices=self.list_devices()
        chosen=self.choose_best(devices)
        sr_ok=False; sd_ok=False
        try: import speech_recognition; sr_ok=True
        except Exception: pass
        try: import sounddevice; sd_ok=True
        except Exception: pass
        provider=str(self.settings.get("stt_provider","auto")).strip().lower()
        model_value=self.settings.get("vosk_model_path") or os.getenv("ALICE_VOSK_MODEL_PATH","")
        model_path=Path(str(model_value)).expanduser() if str(model_value).strip() else None
        model_configured=bool(model_path and model_path.is_dir() and any(model_path.iterdir()))
        vosk_ok=False
        try: import vosk; vosk_ok=True
        except Exception: pass
        cloud_allowed=(str(self.settings.get("allow_cloud_stt",False)).lower() in {"1","true","yes","on"}
                       or os.getenv("ALICE_STT_ALLOW_CLOUD","").lower() in {"1","true","yes","on"})
        if provider not in {"auto","vosk","google"}:
            backend="invalid provider"; recognition_ready=False
        elif provider=="google":
            backend="Google (online)" if cloud_allowed else "Google disabled (audio consent required)"
            recognition_ready=cloud_allowed
        elif model_configured and vosk_ok:
            backend="Vosk (local/offline)"; recognition_ready=True
        elif provider=="vosk":
            backend="Vosk unavailable (model or package missing)"; recognition_ready=False
        elif cloud_allowed:
            backend="Google (online; explicit opt-in)"; recognition_ready=True
        else:
            backend="No recognizer configured (no local model; cloud disabled)"; recognition_ready=False
        return {'ok':bool(chosen and sr_ok and sd_ok), 'speech_recognition':sr_ok,
                'sounddevice':sd_ok, 'device_count':len(devices), 'devices':devices,
                'selected':chosen, 'saved_device':self.settings.get('device_name',''),
                'error':self.settings.get('last_device_error',''), 'recognition_ready':recognition_ready,
                'recognition_backend':backend, 'local_model_configured':model_configured,
                'cloud_audio_opt_in':cloud_allowed}

    def recognize_once(self, timeout=5, phrase_time_limit=12):
        with self.capture_session():
            return self._recognize_once(timeout=timeout, phrase_time_limit=phrase_time_limit)

    def _recognize_once(self, timeout=5, phrase_time_limit=12):
        try:
            import speech_recognition as sr
        except Exception as exc:
            raise RuntimeError('SpeechRecognition is not installed in this ALICE environment.') from exc
        try:
            import sounddevice as sd
            import numpy as np
        except Exception as exc:
            raise RuntimeError('The microphone capture backend is not installed. ALICE needs sounddevice for voice input.') from exc
        devices=self.list_devices(); chosen=self.choose_best(devices)
        if not chosen: raise RuntimeError('No usable microphone input device was detected.')
        samplerate=16000; channels=1
        # SpeechRecognition's Google adapter accepts WAV/PCM AudioData. We capture
        # a bounded clip with sounddevice, then pass it to the adapter.
        seconds=max(1,int(phrase_time_limit))
        started=__import__('time').monotonic()
        with sd.InputStream(device=int(chosen['index']),samplerate=samplerate,channels=channels,dtype='int16') as stream:
            # Small pre-roll so the first syllable is not lost.
            sd.sleep(150)
            frames=[]
            chunk=1024
            while __import__('time').monotonic()-started < seconds:
                data,_=stream.read(chunk); frames.append(data.copy())
                # Let SpeechRecognition-style timeout remain bounded without
                # implementing a second VAD dependency.
        pcm=np.concatenate(frames,axis=0).tobytes() if frames else b''
        if not pcm: return None
        return self._transcribe_pcm(pcm, samplerate, sr)

    def _transcribe_pcm(self, pcm, samplerate, speech_recognition_module):
        """Transcribe captured PCM without uploading it unless cloud STT is opted in."""
        import json
        import os
        provider = str(self.settings.get('stt_provider', 'auto')).strip().lower()
        model_value = self.settings.get('vosk_model_path') or os.getenv('ALICE_VOSK_MODEL_PATH', '')
        model_path = Path(str(model_value)).expanduser() if str(model_value).strip() else None
        model_ready = bool(model_path and model_path.is_dir() and any(model_path.iterdir()))
        if provider not in {'auto', 'vosk', 'google'}:
            raise RuntimeError('Unsupported speech recognizer. Choose auto, vosk, or google.')
        if provider in {'auto', 'vosk'} and model_ready:
            try:
                import vosk
                model = vosk.Model(str(model_path.resolve()))
                recognizer = vosk.KaldiRecognizer(model, samplerate)
                recognizer.AcceptWaveform(pcm)
                result = json.loads(recognizer.FinalResult() or '{}')
                recognized = str(result.get('text', '') or '').strip()
                return recognized or None
            except ImportError as exc:
                raise RuntimeError('A local Vosk model is configured but the vosk package is not installed.') from exc
            except Exception as exc:
                raise RuntimeError('Local Vosk recognition failed: ' + str(exc)[:300]) from exc
        if provider == 'vosk':
            raise RuntimeError('Local Vosk recognition is selected but no valid model directory is configured.')
        cloud_allowed = (str(self.settings.get('allow_cloud_stt', False)).lower() in {'1', 'true', 'yes', 'on'}
                         or os.getenv('ALICE_STT_ALLOW_CLOUD', '').lower() in {'1', 'true', 'yes', 'on'})
        if not cloud_allowed:
            raise RuntimeError('No local speech model is configured. Cloud speech recognition is disabled; configure vosk_model_path or explicitly enable cloud STT.')
        audio = speech_recognition_module.AudioData(pcm, samplerate, 2)
        try:
            return speech_recognition_module.Recognizer().recognize_google(audio)
        except speech_recognition_module.UnknownValueError:
            return None
        except speech_recognition_module.RequestError as exc:
            raise RuntimeError('Opt-in cloud speech recognition service is unavailable: ' + str(exc)) from exc
