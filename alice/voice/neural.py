"""Optional Microsoft Edge neural TTS backend for ALICE.

The backend is opt-in and network-dependent. It uses Microsoft's public Edge
TTS service through the ``edge_tts`` package; it does not ship or redistribute
voice recordings. Windows SAPI remains the offline fallback.
"""
from __future__ import annotations
import asyncio
import os
import re
import shutil
import subprocess
import tempfile
import socket
import time
from threading import RLock
from pathlib import Path

FEMALE_VOICE_PACKS = {
    "Alice US – Aria": {"voice": "en-US-AriaNeural", "locale": "en-US", "gender": "Female"},
    "Alice US – Jenny": {"voice": "en-US-JennyNeural", "locale": "en-US", "gender": "Female"},
    "Alice US – Ava": {"voice": "en-US-AvaNeural", "locale": "en-US", "gender": "Female"},
    "Alice UK – Sonia": {"voice": "en-GB-SoniaNeural", "locale": "en-GB", "gender": "Female"},
    "Alice India – Neerja": {"voice": "en-IN-NeerjaNeural", "locale": "en-IN", "gender": "Female"},
    "Alice Australia – Natasha": {"voice": "en-AU-NatashaNeural", "locale": "en-AU", "gender": "Female"},
}

class NeuralVoiceProvider:
    name = "microsoft_edge_neural"
    # Network reachability changes slowly relative to individual utterances.
    # Reusing a short-lived result avoids a DNS/TCP round trip before every turn.
    _diagnostic_ttl_seconds = 20.0
    _diagnostic_lock = RLock()
    _diagnostic_cache = {}

    @staticmethod
    def split_for_early_audio(text: str, max_chars: int = 260) -> list[str]:
        """Split complete speech into bounded, sentence-aware chunks.

        Text is never discarded: long sentences are split on whitespace and all
        chunks preserve the source characters apart from surrounding whitespace.
        This allows playback to begin after the first chunk is synthesized instead
        of waiting for a very long response to finish synthesis.
        """
        clean = str(text if text is not None else "").strip()
        if not clean:
            return []
        if isinstance(max_chars, bool) or int(max_chars) < 40:
            raise ValueError("max_chars_must_be_at_least_40")
        # Split after sentence-ending punctuation while retaining punctuation.
        sentences = re.split(r"(?<=[.!?])\s+", clean)
        chunks: list[str] = []
        for sentence in sentences:
            remaining = sentence.strip()
            while len(remaining) > int(max_chars):
                cut = remaining.rfind(" ", 0, int(max_chars) + 1)
                if cut < 1:
                    cut = int(max_chars)
                part = remaining[:cut].strip()
                if part:
                    chunks.append(part)
                remaining = remaining[cut:].strip()
            if remaining:
                chunks.append(remaining)
        return chunks

    def __init__(self, root=None):
        self.root = Path(root or Path(__file__).resolve().parents[2]).resolve()
        self.cache = self.root / "alice_workspace" / "runtime" / "voice_cache"
        self.cache.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def available():
        try:
            import edge_tts  # noqa: F401
            return True
        except Exception:
            return False

    def packs(self):
        return [{"id": k, **v, "available": self.available()} for k, v in FEMALE_VOICE_PACKS.items()]

    def diagnose_voice(self, voice: str, *, refresh: bool = False):
        """Diagnose Edge TTS reachability, using a short-lived privacy-safe cache."""
        key = str(voice or "")
        now = time.monotonic()
        with self._diagnostic_lock:
            cached = self._diagnostic_cache.get(key)
            if not refresh and cached and now - cached[0] < self._diagnostic_ttl_seconds:
                return dict(cached[1])
        result={"voice":key,"available":self.available(),"dns":False,"endpoint":False,"ok":False,"error":""}
        if not result["available"]:
            result["error"]="edge-tts is not installed"
        else:
            try:
                socket.getaddrinfo("speech.platform.bing.com",443,type=socket.SOCK_STREAM)
                result["dns"]=True
            except Exception as exc:
                result["error"]=f"DNS resolution failed for speech.platform.bing.com: {type(exc).__name__}"
            if result["dns"]:
                try:
                    with socket.create_connection(("speech.platform.bing.com",443),timeout=3.0):
                        result["endpoint"]=True
                except Exception as exc:
                    result["error"]=f"TLS endpoint is unreachable: {type(exc).__name__}"
            result["ok"] = bool(result["dns"] and result["endpoint"])
        with self._diagnostic_lock:
            self._diagnostic_cache[key] = (now, dict(result))
        return result

    def _play_mp3_windows(self, path: Path, cancel_event=None):
        if os.name != "nt" or not shutil.which("powershell"):
            return False
        script = r'''Add-Type -AssemblyName PresentationCore
$player = New-Object System.Windows.Media.MediaPlayer
try {
  $target = $env:ALICE_TTS_PATH
  if (-not $target -or -not (Test-Path -LiteralPath $target)) { throw "Neural audio file was not found." }
  $player.Open([Uri]$target)
  $deadline=[DateTime]::UtcNow.AddSeconds(10)
  while (-not $player.NaturalDuration.HasTimeSpan) {
    if ([DateTime]::UtcNow -gt $deadline) { throw "Timed out waiting for neural audio metadata." }
    Start-Sleep -Milliseconds 50
  }
  $player.Volume=1.0; $player.Play()
  $duration=$player.NaturalDuration.TimeSpan
  $deadline=[DateTime]::UtcNow.AddSeconds([Math]::Max(20,$duration.TotalSeconds+10))
  while ($player.Position -lt $duration) {
    if ([DateTime]::UtcNow -gt $deadline) { throw "Timed out while playing neural audio." }
    Start-Sleep -Milliseconds 80
  }
  exit 0
} catch { [Console]::Error.WriteLine($_.Exception.Message); exit 2 } finally { $player.Close() }
'''
        env=os.environ.copy(); env["ALICE_TTS_PATH"]=str(path)
        proc=subprocess.Popen(["powershell","-NoProfile","-NonInteractive","-STA","-ExecutionPolicy","Bypass","-Command",script],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        deadline=time.time()+120
        while proc.poll() is None:
            if cancel_event is not None and cancel_event.is_set():
                try: proc.terminate()
                except Exception: pass
                try: proc.wait(timeout=2)
                except Exception:
                    try: proc.kill()
                    except Exception: pass
                return False
            if time.time()>deadline:
                try: proc.terminate()
                except Exception: pass
                raise RuntimeError("Timed out while playing neural audio.")
            time.sleep(0.05)
        if proc.returncode!=0:
            raise RuntimeError((proc.stderr or proc.stdout or "Windows neural playback failed").strip()[:500])
        return True

    async def _save(self, text: str, voice: str, path: Path):
        import edge_tts
        # Keep the provider's natural defaults unless the user explicitly sets
        # a supported Edge TTS prosody value in the environment.
        rate = os.getenv("ALICE_TTS_RATE", "+0%")
        pitch = os.getenv("ALICE_TTS_PITCH", "+0Hz")
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        await communicate.save(str(path))

    def speak(self, text: str, voice: str, cancel_event=None) -> bool:
        if not self.available():
            raise RuntimeError("Microsoft neural voice backend is not installed. Install edge-tts to enable it.")
        diagnostic=self.diagnose_voice(voice)
        if not diagnostic.get("ok"):
            raise RuntimeError(diagnostic.get("error") or "Microsoft neural TTS endpoint is unavailable")
        chunks = self.split_for_early_audio(str(text))
        if not chunks:
            return False
        # Synthesize and play bounded chunks sequentially. This reduces time to
        # first audible speech on long responses without dropping the tail.
        for chunk in chunks:
            if cancel_event is not None and cancel_event.is_set():
                return False
            fd, tmp = tempfile.mkstemp(prefix="alice_tts_", suffix=".mp3", dir=str(self.cache))
            os.close(fd)
            path = Path(tmp)
            try:
                last=None
                for attempt in range(2):
                    try:
                        asyncio.run(self._save(chunk, voice, path))
                        break
                    except Exception as exc:
                        last=exc
                        if cancel_event is not None and cancel_event.is_set(): return False
                        if attempt==0: time.sleep(0.15)
                else:
                    raise RuntimeError(str(last)[:500])
                if cancel_event is not None and cancel_event.is_set():
                    return False
                if not self._play_mp3_windows(path,cancel_event=cancel_event):
                    return False
            finally:
                try: path.unlink(missing_ok=True)
                except Exception: pass
        return True
