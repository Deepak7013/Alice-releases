"""Opt-in continuous Jarvis-style listening using ALICE's existing audio path.

Audio is sent to Google's SpeechRecognition service only when the user has
explicitly enabled ``allow_cloud_stt``. Local Whisper and sherpa-onnx process
audio on-device. Translation is separately opt-in and can use installed Argos
offline packages or the explicitly selected online translator. No audio or
transcript is written to a diagnostic log here.
"""
from __future__ import annotations

import math
import struct
import threading
import time
from contextlib import ExitStack
from dataclasses import dataclass
from typing import Callable


def _enabled(value) -> bool:
    if isinstance(value,bool): return value
    return str(value or "").strip().lower() in {"1","true","yes","on"}


@dataclass(frozen=True)
class ListeningConfig:
    sample_rate: int = 16000
    block_size: int = 1024
    ambient_calibration_seconds: float = 1.0
    energy_threshold_multiplier: float = 2.5
    minimum_energy_threshold: float = 180.0
    pause_threshold: float = 0.8
    phrase_threshold: float = 0.25
    listen_timeout: float = 10.0
    recognition_timeout: float = 8.0
    recognition_backend: str = "google"
    whisper_model: str = "small.en"
    streaming_model_dir: str = ""
    translate_enabled: bool = False
    translation_backend: str = "argos_offline"
    source_language: str = "auto"
    target_language: str = "en"

    @classmethod
    def from_settings(cls, settings):
        def number(name, default, minimum, maximum):
            try: value=float(settings.get(name, default))
            except (TypeError, ValueError): value=float(default)
            return min(max(value, minimum), maximum)
        return cls(
            ambient_calibration_seconds=number("ambient_calibration_seconds", 1.0, 0.2, 5.0),
            energy_threshold_multiplier=number("energy_threshold_multiplier", 2.5, 1.0, 8.0),
            minimum_energy_threshold=number("minimum_energy_threshold", 180.0, 20.0, 5000.0),
            pause_threshold=number("pause_threshold", 0.8, 0.2, 3.0),
            phrase_threshold=number("phrase_threshold", 0.25, 0.1, 2.0),
            listen_timeout=number("listen_timeout", 10.0, 2.0, 120.0),
            recognition_timeout=number("recognition_timeout", 8.0, 2.0, 30.0),
            recognition_backend=str(settings.get("recognition_backend", "google") or "google").strip().lower(),
            # This setting accepts either a Faster-Whisper model name or a local
            # CTranslate2 model directory, which can be longer than 32 chars.
            whisper_model=str(settings.get("whisper_model", "small.en") or "small.en").strip()[:1024],
            streaming_model_dir=str(settings.get("streaming_model_dir", "") or "").strip()[:1024],
            translate_enabled=_enabled(settings.get("translate_enabled", False)),
            translation_backend=str(settings.get("translation_backend", "argos_offline") or "argos_offline").strip().lower(),
            source_language=str(settings.get("source_language", "auto") or "auto").strip()[:16],
            target_language=str(settings.get("target_language", "en") or "en").strip()[:16],
        )


def _rms_int16(pcm: bytes) -> float:
    count=len(pcm)//2
    if not count: return 0.0
    samples=struct.unpack("<"+"h"*count, pcm[:count*2])
    return math.sqrt(sum(sample*sample for sample in samples)/count)


class JarvisAdvancedListener:
    """Calibrate ambient noise, segment repeated utterances, and report status.

    The capture device is supplied by MicrophoneManager (sounddevice), avoiding
    a second PyAudio capture stack. ``on_status`` and ``on_transcript`` should
    enqueue UI work rather than touching Tk from this daemon worker.
    """
    def __init__(self, microphone, *, on_status: Callable[[str], object] | None = None,
                 on_transcript: Callable[[str, str | None], object] | None = None,
                 on_partial: Callable[[str], object] | None = None,
                 stream_factory=None, clock=None):
        self.microphone=microphone
        self.on_status=on_status or (lambda _message: None)
        self.on_transcript=on_transcript or (lambda _text, _translated: None)
        self.on_partial=on_partial or (lambda _text: None)
        self.stream_factory=stream_factory
        self.clock=clock or time.monotonic
        self._stop=threading.Event()
        self._thread: threading.Thread | None=None
        self._state_lock=threading.RLock()
        self._translation_lock=threading.Lock()
        self._whisper_model=None
        self._whisper_model_name=None
        self._sherpa_recognizer=None
        self._sherpa_model_dir=None

    @property
    def running(self):
        with self._state_lock:
            return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())

    @property
    def stopping(self):
        with self._state_lock:
            return bool(self._thread and self._thread.is_alive() and self._stop.is_set())

    def start(self) -> bool:
        with self._state_lock:
            if self._thread and self._thread.is_alive():
                return False
            backend=str(self.microphone.settings.get("recognition_backend", "google") or "google").strip().lower()
            if backend not in {"google", "local_whisper", "sherpa_streaming"}:
                raise RuntimeError("Choose streaming sherpa, local Whisper, or Google for speech recognition.")
            if backend == "google" and not _enabled(self.microphone.settings.get("allow_cloud_stt", False)):
                raise RuntimeError("Jarvis Advanced Listening sends captured audio to Google. Enable cloud speech recognition first.")
            if backend == "local_whisper":
                try: import faster_whisper  # noqa: F401
                except Exception as exc: raise RuntimeError("Install the optional faster-whisper dependency for local recognition.") from exc
            if backend == "sherpa_streaming":
                try: import sherpa_onnx  # noqa: F401
                except Exception as exc: raise RuntimeError("Install requirements_streaming_stt.txt in ALICE's environment.") from exc
            self._stop.clear()
            self._thread=threading.Thread(target=self._run, name="AliceJarvisAdvancedListener", daemon=True)
            self._thread.start()
            return True

    def stop(self, timeout: float = 1.0) -> bool:
        self._stop.set()
        with self._state_lock: thread=self._thread
        if thread and thread is not threading.current_thread():
            thread.join(max(0.0, min(float(timeout), 2.0)))
        return not bool(thread and thread.is_alive())

    def _status(self, message):
        try: self.on_status(str(message)[:300])
        except Exception: pass

    def _transcribe(self, pcm: bytes, samplerate: int, config: ListeningConfig):
        if config.recognition_backend == "local_whisper":
            import numpy as np
            from faster_whisper import WhisperModel
            if self._whisper_model is None or self._whisper_model_name != config.whisper_model:
                self._status(f"Loading local Whisper model {config.whisper_model}…")
                self._whisper_model=WhisperModel(config.whisper_model,device="cpu",compute_type="int8")
                self._whisper_model_name=config.whisper_model
            samples=np.frombuffer(pcm,dtype="<i2").astype(np.float32)/32768.0
            segments,_info=self._whisper_model.transcribe(samples,language="en",beam_size=5,vad_filter=True)
            text=" ".join(str(segment.text).strip() for segment in segments).strip()
        else:
            import speech_recognition as sr
            recognizer=sr.Recognizer()
            recognizer.operation_timeout=config.recognition_timeout
            audio=sr.AudioData(pcm, samplerate, 2)
            text=recognizer.recognize_google(audio).strip()
        if not text: return
        self._deliver_transcript(text, config)

    def _deliver_transcript(self, text: str, config: ListeningConfig, *, detected_language: str = ""):
        translated=None
        if config.translate_enabled:
            source=config.source_language
            if source == "auto":
                # Every active recognition choice in this C43 UI uses English input.
                source="en" if config.recognition_backend in {"google", "local_whisper", "sherpa_streaming"} else detected_language
            if not source or not config.target_language:
                raise RuntimeError("Set explicit source and target language codes for offline translation.")
            if source != config.target_language:
                backend=config.translation_backend
                if backend == "argos_offline":
                    try:
                        from argostranslate.translate import get_installed_languages
                    except ImportError as exc:
                        raise RuntimeError(
                            "Offline translation is unavailable: install Argos Translate "
                            "and the requested language packages."
                        ) from exc
                    languages=get_installed_languages()
                    from_language=next((language for language in languages if language.code==source),None)
                    to_language=next((language for language in languages if language.code==config.target_language),None)
                    if not from_language or not to_language:
                        raise RuntimeError(
                            f"Offline translation pair {source}→{config.target_language} is not installed. "
                            "Install the Argos language packages, then try again."
                        )
                    translator=from_language.get_translation(to_language)
                    if translator is None:
                        raise RuntimeError(f"No offline translation path is installed for {source}→{config.target_language}.")
                    translate=lambda value, _to, from_language=None: translator.translate(value)
                elif backend == "mtranslate_online":
                    from mtranslate import translate
                else:
                    raise RuntimeError("Choose Argos offline or mtranslate online for translation.")
                translated=self._translate_bounded(translate,text,config,source_language=source)
                if not translated:
                    raise RuntimeError("Translation returned no text.")
        self.on_transcript(text, translated)

    def _translate_bounded(self, translate, text, config, *, source_language: str | None = None):
        if not self._translation_lock.acquire(blocking=False):
            raise TimeoutError("A previous translation request has not returned; no duplicate request was started.")
        completed=threading.Event(); result={}
        def work():
            try: result["text"]=translate(text,config.target_language,from_language=source_language or config.source_language)
            except Exception as exc: result["error"]=exc
            finally:
                self._translation_lock.release(); completed.set()
        threading.Thread(target=work,name="AliceJarvisTranslation",daemon=True).start()
        if not completed.wait(config.recognition_timeout):
            raise TimeoutError("Translation service timed out; listening will continue without a translation.")
        if "error" in result: raise result["error"]
        return str(result.get("text","") or "").strip()

    def _make_stream(self, device, config):
        if self.stream_factory:
            return self.stream_factory(device=device, samplerate=config.sample_rate,
                                       channels=1, dtype="int16", blocksize=config.block_size)
        try:
            import sounddevice as sd
        except Exception as exc:
            raise RuntimeError("Install the optional sounddevice audio dependency to use microphone input.") from exc
        return sd.InputStream(device=int(device["index"]), samplerate=config.sample_rate,
                              channels=1, dtype="int16", blocksize=config.block_size)

    @staticmethod
    def _ordered_devices(microphone, devices):
        """Try the selected/preferred input first, then the OS default and remaining inputs."""
        preferred=microphone.choose_best(devices)
        default=next((device for device in devices if device.get("default")),None)
        ordered=[]
        for device in (preferred,default,*devices):
            if device is not None and not any(existing.get("index")==device.get("index") for existing in ordered):
                ordered.append(device)
        return ordered

    def _run(self):
        config=ListeningConfig.from_settings(self.microphone.settings)
        try:
            backend=config.recognition_backend
            if backend == "local_whisper":
                try: import faster_whisper  # noqa: F401
                except Exception as exc: raise RuntimeError("Install the optional faster-whisper dependency for local recognition.") from exc
            elif backend == "sherpa_streaming":
                from .streaming_stt import create_online_recognizer
                model_dir=config.streaming_model_dir or None
                if self._sherpa_recognizer is None or self._sherpa_model_dir != str(model_dir or ""):
                    self._status("Loading the local streaming speech model…")
                    self._sherpa_recognizer=create_online_recognizer(model_dir)
                    self._sherpa_model_dir=str(model_dir or "")
            else:
                try: import speech_recognition  # noqa: F401
                except Exception as exc: raise RuntimeError("Install the optional SpeechRecognition dependency for Jarvis mode.") from exc
            devices=self.microphone.list_devices()
            candidates=self._ordered_devices(self.microphone,devices)
            if not candidates: raise RuntimeError("No usable microphone input device was detected.")
            with self.microphone.capture_session():
                with ExitStack() as streams:
                    stream=None; device=None; open_errors=[]
                    for candidate in candidates:
                        try:
                            stream=streams.enter_context(self._make_stream(candidate,config))
                            device=candidate
                            break
                        except Exception as exc:
                            open_errors.append(f"{candidate.get('name','input')}: {str(exc)[:100]}")
                            self._status(f"Microphone {candidate.get('name','input')} could not open; trying another available input.")
                    if stream is None:
                        details="; ".join(open_errors[:3])
                        raise RuntimeError("No microphone input could be opened."+(" "+details if details else ""))
                    sherpa_stream=None
                    if backend == "sherpa_streaming":
                        sherpa_stream=self._sherpa_recognizer.create_stream()
                        self._status(f"Listening continuously on {device['name']} • local streaming model; audio stays on this device.")
                    else:
                        self._status(f"Calibrating ambient noise on {device['name']}…")
                        noise=[]
                        calibration_blocks=max(1, math.ceil(config.ambient_calibration_seconds*config.sample_rate/config.block_size))
                        for _ in range(calibration_blocks):
                            if self._stop.is_set(): return
                            data, overflowed=stream.read(config.block_size)
                            if overflowed: self._status("Audio input overflow during calibration; continuing with available samples.")
                            raw=data if isinstance(data,(bytes,bytearray,memoryview)) else data.tobytes()
                            noise.append(_rms_int16(bytes(raw)))
                        noise.sort()
                        ambient=noise[len(noise)//2] if noise else 0.0
                        threshold=max(config.minimum_energy_threshold, ambient*config.energy_threshold_multiplier)
                        service="local Whisper; audio stays on this device" if backend=="local_whisper" else "Google; audio is sent online"
                        self._status(f"Listening continuously (threshold {threshold:.0f}); recognition uses {service}.")
                    frames=[]; active=False; silence_blocks=0; phrase_blocks=0; voiced_blocks=0; last_partial=""
                    last_speech=self.clock(); last_timeout=last_speech
                    pause_blocks=max(1, math.ceil(config.pause_threshold*config.sample_rate/config.block_size))
                    min_phrase_blocks=max(1, math.ceil(config.phrase_threshold*config.sample_rate/config.block_size))
                    while not self._stop.is_set():
                        data, overflowed=stream.read(config.block_size)
                        if overflowed: self._status("Microphone reported an input overflow; listening continues.")
                        pcm=bytes(data) if isinstance(data,(bytes,bytearray,memoryview)) else data.tobytes()
                        if backend == "sherpa_streaming":
                            from .streaming_stt import pcm16_to_float
                            sherpa_stream.accept_waveform(config.sample_rate, pcm16_to_float(pcm))
                            while self._sherpa_recognizer.is_ready(sherpa_stream):
                                self._sherpa_recognizer.decode_stream(sherpa_stream)
                            partial=self._sherpa_recognizer.get_result(sherpa_stream).strip()
                            if partial and partial != last_partial:
                                self.on_partial(partial)
                                last_partial=partial
                            if self._sherpa_recognizer.is_endpoint(sherpa_stream):
                                final_text=partial
                                self._sherpa_recognizer.reset(sherpa_stream)
                                last_partial=""
                                self.on_partial("")
                                if final_text and not self._stop.is_set():
                                    try: self._deliver_transcript(final_text, config)
                                    except Exception as exc: self._status(self._recognition_error(exc))
                                    if not self._stop.is_set():
                                        self._status("Listening continuously; say another phrase or press Stop.")
                            continue
                        energy=_rms_int16(pcm); now=self.clock()
                        if energy>=threshold:
                            if not active:
                                active=True; frames=[]; phrase_blocks=0; silence_blocks=0; voiced_blocks=0
                            last_speech=now; silence_blocks=0; phrase_blocks+=1; voiced_blocks+=1; frames.append(pcm)
                        elif active:
                            frames.append(pcm); phrase_blocks+=1; silence_blocks+=1
                            if silence_blocks>=pause_blocks:
                                segment=b"".join(frames); completed_voiced_blocks=voiced_blocks
                                active=False; frames=[]; phrase_blocks=0; silence_blocks=0; voiced_blocks=0
                                if completed_voiced_blocks>=min_phrase_blocks and not self._stop.is_set():
                                    self._status("Recognizing phrase…")
                                    try: self._transcribe(segment, config.sample_rate, config)
                                    except Exception as exc:
                                        self._status(self._recognition_error(exc))
                                    if not self._stop.is_set(): self._status("Listening continuously; say another phrase or press Stop.")
                        elif now-last_speech>=config.listen_timeout and now-last_timeout>=config.listen_timeout:
                            self._status("No speech detected yet; still listening.")
                            last_timeout=now
        except Exception as exc:
            if not self._stop.is_set(): self._status(self._recognition_error(exc))
        finally:
            self._status("Jarvis Advanced Listening stopped; microphone released.")

    @staticmethod
    def _recognition_error(exc):
        try:
            import speech_recognition as sr
            if isinstance(exc, sr.UnknownValueError): return "Speech was not recognized; continuing to listen."
            if isinstance(exc, sr.RequestError): return "Google recognition/network error: "+str(exc)[:180]
        except Exception: pass
        if isinstance(exc, ImportError) or "mtranslate" in str(exc).lower():
            return "Translation dependency/status: "+str(exc)[:180]
        return "Listening error: "+str(exc)[:180]
