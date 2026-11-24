"""Fast adaptive multi-provider AI router with streaming support."""
import base64, mimetypes, os, time, threading, socket, re, ipaddress
from urllib.parse import urlsplit
from pathlib import Path
from .health_memory import ProviderHealthMemory
from .runtime_policy import RuntimePolicy

# Always load configuration from the installed Alice root. The launcher may be
# started by Task Scheduler, Explorer, or another process with an unrelated cwd.
_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
class ProviderError(RuntimeError): pass


class Router:
    """Route Alice requests to an available provider and learn which is fastest.

    Provider calls are budget-aware and bounded. A provider error must never create
    a retry storm or leave the UI with a blank answer. Remote output budgets are
    intentionally capped even when an environment variable asks for a huge value.

    Explicit provider choices remain authoritative. With ALICE_PROVIDER=auto,
    Alice keeps the configured primary as the cold-start preference, then uses
    observed latency/reliability to prefer faster successful providers.
    """

    _PREFERENCE = ("gemini", "local")
    _HOSTED = ("openai", "anthropic", "groq", "openrouter", "nvidia")
    _HOSTED_CONFIG = {
        "openai": ("OPENAI_API_KEY", "OPENAI_MODEL", "https://api.openai.com/v1"),
        "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "https://api.anthropic.com/v1"),
        "groq": ("GROQ_API_KEY", "GROQ_MODEL", "https://api.groq.com/openai/v1"),
        "openrouter": ("OPENROUTER_API_KEY", "OPENROUTER_MODEL", "https://openrouter.ai/api/v1"),
        "nvidia": ("NVIDIA_API_KEY", "NVIDIA_MODEL", "https://integrate.api.nvidia.com/v1"),
    }

    def _runtime_mode(self):
        policy=getattr(self,"runtime_policy",None)
        return getattr(policy,"mode","local_required")

    @staticmethod
    def _provider_label(provider):
        return {"openai":"OpenAI","anthropic":"Anthropic","groq":"Groq",
                "openrouter":"OpenRouter","nvidia":"NVIDIA","gemini":"Gemini"}.get(
                    str(provider).lower(),str(provider).title())

    @staticmethod
    def _is_loopback_url(value):
        """Accept only explicit HTTP(S) endpoints on the current machine."""
        try:
            parsed = urlsplit(str(value).strip())
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                return False
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                return False
            host = parsed.hostname.rstrip(".").lower()
            if host == "localhost":
                return True
            return ipaddress.ip_address(host).is_loopback
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _local_service_detected():
        """Detect a local OpenAI-compatible service (Ollama default) without an API key."""
        try:
            configured = os.getenv("OLLAMA_HOST", "127.0.0.1:11434").strip()
            endpoint = configured if "://" in configured else "http://" + configured
            parsed = urlsplit(endpoint)
            if not Router._is_loopback_url(endpoint) or parsed.port is None:
                return False
            with socket.create_connection((parsed.hostname, parsed.port), timeout=0.35):
                return True
        except Exception:
            return False

    def __init__(self, provider=None):
        self.provider="gemini"
        self.primary="gemini"
        self.local_model=os.getenv("LOCAL_AI_MODEL","llama3.2:latest")
        # Simple conversation may use a smaller local model; planning continues
        # to use local_model so the task executor keeps the stronger planner.
        # The 270M Gemma is the fast lane for short, read-only conversational
        # turns. Users can select the 1B model from Brain Setup for better
        # phrasing; all planning and substantive work stays on local_model.
        self.local_fast_model=os.getenv("ALICE_LOCAL_FAST_MODEL","gemma3:270m")
        self.local_base=os.getenv("LOCAL_AI_BASE_URL","http://localhost:11434/v1")
        self.gemini_model=os.getenv("GEMINI_MODEL","gemini-3.8-flash")
        self.local_enabled=os.getenv("ALICE_ENABLE_LOCAL_AI","auto").lower() in {"1","true","yes","on"} or (os.getenv("ALICE_ENABLE_LOCAL_AI","auto").lower()=="auto" and self._local_service_detected())
        self.openrouter_free_only=False
        self._clients={}
        self._health={}
        self._health_lock=threading.Lock()
        self._active_provider=None
        self._health_memory=ProviderHealthMemory()
        self.runtime_policy=RuntimePolicy.from_env()

    def local_status(self):
        """Return a truthful local-model readiness report without requiring a key.

        Ollama exposes its local model inventory through /api/tags. Socket reachability
        alone is not enough: a running service with no requested model cannot engineer.
        """
        import json as _json, urllib.request as _urlreq
        host=os.getenv("OLLAMA_HOST", "127.0.0.1:11434")
        base=host if host.startswith(("http://", "https://")) else "http://"+host
        base=base.rstrip("/")
        if base.endswith("/v1"): base=base[:-3]
        model=os.getenv("LOCAL_AI_MODEL", self.local_model)
        installed=bool(__import__("shutil").which("ollama"))
        if not self._is_loopback_url(base):
            return {"installed":installed,"reachable":False,"model":model,"model_available":False,
                    "models":[],"base_url":base,"api_key_required":False,
                    "error":"Local inference endpoint must use localhost or a loopback IP address."}
        try:
            with _urlreq.urlopen(base+"/api/tags", timeout=1.5) as resp:
                data=_json.loads(resp.read().decode("utf-8", "replace"))
            names=[]
            for item in data.get("models", []) if isinstance(data, dict) else []:
                if isinstance(item, dict): names.append(str(item.get("name") or item.get("model") or ""))
            reachable=True
            model_available=any(n==model or n.split(":",1)[0]==model.split(":",1)[0] and model.endswith(":latest") for n in names)
            return {"installed":installed,"reachable":reachable,"model":model,"model_available":model_available,"models":names,"base_url":base,"api_key_required":False}
        except Exception as exc:
            return {"installed":installed,"reachable":False,"model":model,"model_available":False,"models":[],"base_url":base,"api_key_required":False,"error":str(exc)[:300]}

    def engineering_ask(self, prompt, image_path=None, max_tokens=None):
        """Ask the engineering brain while respecting the global runtime policy."""
        self.reload_config()
        local_first=True
        require_local=True
        allow_remote=False
        # Self-engineering may use a reachable local model even when an older .env
        # explicitly disabled normal local routing. This prevents an upgrade from
        # requiring the user to edit provider settings just to unlock local engineering.
        from alice.engineering.local_governor import LocalEngineeringGovernor
        status=self.local_status() if local_first else {"model_available":False,"reachable":False,"model":self.local_model}
        governor=LocalEngineeringGovernor(_PACKAGE_ROOT, status_provider=lambda: status)
        route=governor.route(status, local_first=local_first, require_local=require_local,
                             remote_fallback_allowed=allow_remote)
        governor.record(route)
        errors=[]
        if route.mode in {"local", "local_required"} and status.get("model_available"):
            try:
                result=self._call_one("local", prompt, image_path, max_tokens)
                governor.record(route, outcome="local_success")
                return result
            except Exception as exc:
                errors.append("local: "+str(exc))
                governor.record(route, outcome="local_failure")
                raise ProviderError("Local self-engineering model failed. "+str(exc))
        if route.mode == "blocked":
            raise ProviderError("Self-engineering has no permitted reasoning provider. "+route.reason)
        if errors and not allow_remote:
            raise ProviderError("No self-engineering provider succeeded. "+" | ".join(errors))
        raise ProviderError("ALICE runs AI reasoning locally. Install and start the configured Ollama model before using self-engineering. " + route.reason)

    def reload_config(self):
        """Refresh configured provider selection and local inference settings."""
        self.runtime_policy=RuntimePolicy.from_env()
        self.provider="gemini"
        self.primary=self.provider
        self.openrouter_free_only=False
        self.local_model=os.getenv("LOCAL_AI_MODEL", self.local_model)
        self.local_base=os.getenv("LOCAL_AI_BASE_URL", self.local_base)
        _local_setting=os.getenv("ALICE_ENABLE_LOCAL_AI", "auto").lower()
        self.local_enabled=_local_setting in {"1","true","yes","on"} or (_local_setting=="auto" and self._local_service_detected())
        self.gemini_model=str(os.getenv("GEMINI_MODEL","gemini-3.8-flash") or "gemini-3.8-flash").strip()
        self.provider=self.primary_provider() or "local"
        self.primary=self.provider
        self._clients.clear()
        self._gemini_client_obj=None
        return self.available()

    def available(self):
        result={name:bool(str(os.getenv(key, "") or "").strip())
                for name,(key,_model,_base) in self._HOSTED_CONFIG.items()}
        result.update({"gemini":bool(str(os.getenv("GEMINI_API_KEY", "") or "").strip()),
                "local":self.local_enabled,"tfidf":True}
        )
        return result

    @staticmethod
    def _is_budget_error(exc):
        text=str(exc).lower()
        return any(token in text for token in (
            "status code: 402", " 402", "http 402", "payment required",
            "more credits", "fewer max_tokens", "insufficient credits",
            "context length", "maximum context", "max_tokens",
        ))

    @staticmethod
    def _is_rate_limit_error(exc):
        text=str(exc).lower()
        return "429" in text or "rate limit" in text or "too many requests" in text

    @staticmethod
    def _estimate_tokens(text):
        # Conservative enough for routing; this is not a tokenizer and is only
        # used to bound output requests before a provider sees them.
        return max(1, (len(str(text)) + 3) // 4)

    def _safe_max_tokens(self, prompt, requested=None):
        env_cap=os.getenv("ALICE_PROVIDER_MAX_OUTPUT_TOKENS", "2048")
        try: cap=max(128,min(int(env_cap),8192))
        except Exception: cap=2048
        try:
            requested=int(requested) if requested is not None else cap
        except Exception:
            requested=cap
        # Keep enough room for the prompt under common 16k/32k provider windows.
        prompt_tokens=self._estimate_tokens(prompt)
        context_cap=max(1, min(cap, 12000 - min(prompt_tokens, 9000)))
        return max(1,min(requested,context_cap,cap))

    @staticmethod
    def _retry_budgets(initial):
        values=[]
        for n in (initial, 1024, 512, 256):
            n=max(1,int(n))
            if n not in values: values.append(n)
        return values[:4]

    @staticmethod
    def _budget_hint(exc):
        """Extract a provider's affordable output budget when an HTTP 402 exposes one."""
        text=str(exc)
        patterns=(
            r"can\s+only\s+afford\s+(?:up\s+to\s+)?([0-9,]+)",
            r"afford[^0-9]{0,30}([0-9,]+)\s+tokens?",
            r"maximum[^0-9]{0,20}([0-9,]+)\s+tokens?",
        )
        for pat in patterns:
            m=re.search(pat,text,re.I)
            if m:
                try:return max(1,int(m.group(1).replace(',','')))
                except ValueError: pass
        return None

    @staticmethod
    def _bounded_rate_retry(attempt):
        # One short retry is useful for transient 429s; never spin on a provider.
        if attempt == 0:
            time.sleep(0.35)
            return True
        return False

    @staticmethod
    def _gemini_http_status(exc):
        code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        try:
            return int(code)
        except (TypeError, ValueError):
            match = re.search(r"\b(?:HTTP\s*)?(50[0-4])\b", str(exc), re.I)
            return int(match.group(1)) if match else None

    @classmethod
    def _is_gemini_transient_server_error(cls, exc):
        # Retry only service/gateway failures, once. Never retry auth, model,
        # malformed-request, or quota errors; those need configuration changes.
        return cls._gemini_http_status(exc) in {500, 502, 503, 504}

    @classmethod
    def _gemini_request_with_retry(cls, request):
        for attempt in range(2):
            try:
                return request()
            except Exception as exc:
                if attempt or not cls._is_gemini_transient_server_error(exc):
                    raise
                time.sleep(0.6)

    @staticmethod
    def _clean_provider_error(provider, exc):
        text=str(exc).replace("\n"," ").strip()
        low=text.lower()
        if "402" in low or "more credits" in low or "fewer max_tokens" in low:
            return (f"{provider} returned HTTP 402 (payment, credit, or request-budget restriction). "
                    "No further budget retries were made; ALICE does not change billing. "
                    "Check the provider activity/error details and configured model.")
        if "429" in low or "rate limit" in low:
            if provider == "gemini":
                return "Gemini is rate-limited or its quota is exhausted. ALICE will not switch to another hosted provider automatically. Check AI Studio usage and retry after quota reset."
            return f"{provider} is rate-limited. ALICE will make one bounded retry and then use another configured provider if available."
        if provider == "gemini":
            code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
            try:
                code = int(code)
            except (TypeError, ValueError):
                code = None
            if code in (401, 403) or "api key not valid" in low or "unauthorized" in low:
                return "Gemini authentication failed. Check the locally saved Gemini API key and AI Studio project access."
            if code == 429:
                return "Gemini returned HTTP 429: the project has hit a request-rate or quota limit. Check AI Studio Usage/Rate Limit and retry after reset; ALICE will not switch hosted providers."
            if code == 404:
                return "Gemini returned HTTP 404: the configured model or endpoint was not found or is unavailable to this project. Check the model ID and AI Studio model access."
            if code == 400:
                return "Gemini returned HTTP 400: the request or a model option was rejected. Check the selected model and ALICE request settings."
            if code is not None and 500 <= code <= 599:
                if code == 503:
                    detail = "Gemini is temporarily unavailable. Wait briefly and retry."
                elif code == 504:
                    detail = "Gemini's server deadline expired. Retry later or use a shorter request."
                else:
                    detail = "Gemini reported a server-side failure. Retry later and check AI Studio status/logs."
                return f"Gemini returned HTTP {code}: {detail} This does not by itself indicate an invalid API key. ALICE did not switch providers."
            if "timeout" in low or "timed out" in low:
                return "Gemini request timed out. Check the connection and retry."
            if "google-genai" in low or "no module named" in low:
                return "Gemini support is not installed. Install the project's requirements, including google-genai."
            return f"Gemini request failed ({type(exc).__name__}). Check the configured model, network, and AI Studio quota."
        key_name=Router._HOSTED_CONFIG.get(provider, ("", "", ""))[0]
        secret=str(os.getenv(key_name, "") or "").strip() if key_name else ""
        if secret: text=text.replace(secret,"[redacted]")
        return f"{provider} failed: {text[:240]}"

    def _record_success(self, provider, elapsed):
        with self._health_lock:
            h=self._health.setdefault(provider,{"success":0,"fail":0,"ema":None,"last_error":""})
            h["success"] += 1
            h["ema"] = elapsed if h["ema"] is None else (0.70*h["ema"] + 0.30*elapsed)
            h["last_error"]=""
        try: self._health_memory.record(provider, ok=True, latency=elapsed)
        except Exception: pass

    def _record_failure(self, provider, error):
        with self._health_lock:
            h=self._health.setdefault(provider,{"success":0,"fail":0,"ema":None,"last_error":""})
            h["fail"] += 1
            safe_error=self._clean_provider_error(provider,error)
            h["last_error"]=safe_error[:300]
        try: self._health_memory.record(provider, ok=False, error=safe_error)
        except Exception: pass

    def health(self):
        with self._health_lock:
            live={k:dict(v) for k,v in self._health.items()}
        try:
            live["persistent"]=self._health_memory.snapshot()
        except Exception: pass
        return live

    def primary_provider(self):
        mode=self._runtime_mode()
        if mode == "gemini_primary": return "gemini"
        for provider in self._HOSTED:
            if mode == provider + "_primary": return provider
        return "local" if getattr(self,"local_enabled",False) and self.local_status().get("model_available") else None

    def _auto_order(self):
        primary=self.primary_provider()
        if primary and primary != "local": return [primary]
        return ["local"] if getattr(self,"local_enabled",False) and self.local_status().get("model_available") else []

    def _order(self):
        return self._auto_order()

    @staticmethod
    def _data_url(path):
        p=Path(path); mime=mimetypes.guess_type(p.name)[0] or "image/png"
        return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"

    def _call_one(self,p,prompt,image_path,max_tokens):
        if p not in {"local", "gemini", *self._HOSTED}:
            raise ProviderError(f"Provider '{p}' is disabled in this ALICE build.")
        mode=self._runtime_mode()
        if mode == "local_required" and p != "local":
            raise ProviderError("Hosted AI providers are blocked in local-only mode.")
        selected=("gemini" if mode == "gemini_primary" else
                  mode[:-8] if mode.endswith("_primary") else None)
        if selected and p != selected:
            raise ProviderError(f"Provider '{p}' is blocked because ALICE is explicitly configured for '{selected}'.")
        started=time.monotonic(); self._active_provider=p
        initial=self._safe_max_tokens(prompt,max_tokens)
        last=None
        budgets=self._retry_budgets(initial)
        attempt=0
        while attempt < len(budgets):
            budget=budgets[attempt]
            try:
                result=getattr(self,f"_ask_{p}")(prompt,image_path,max_tokens=budget)
                if not str(result or "").strip():
                    raise ProviderError(f"{p} returned an empty response")
                self._record_success(p,time.monotonic()-started)
                return result
            except Exception as e:
                last=e
                budget_error=self._is_budget_error(e)
                # Do not persist raw provider 402/error bodies in health memory:
                # they can contain account or request metadata. Keep only a
                # coarse diagnostic while retaining the exception in-process
                # for bounded parsing of an explicit affordable-token hint.
                self._record_failure(p,"provider request budget restriction" if budget_error else e)
                if budget_error:
                    hint=self._budget_hint(e)
                    # Generic 402 responses are not replayed at successively
                    # smaller budgets. Permit one materially smaller retry only
                    # when the provider explicitly reports an affordable cap.
                    if hint is not None and hint < budget and attempt == 0:
                        # Prefer the provider-reported affordable amount, but
                        # keep it within ALICE's own safety cap.
                        next_budget=min(hint, max(128, budget-1))
                        # Skip the generic descending budget ladder and go
                        # directly to the explicitly reported affordable cap.
                        budgets=budgets[:attempt+1]+[next_budget]
                    else:
                        break
                elif self._is_rate_limit_error(e):
                    if self._bounded_rate_retry(attempt):
                        attempt += 1
                        continue
                    break
                else:
                    break
            attempt += 1
        raise ProviderError(self._clean_provider_error(p,last or "unknown provider error"))

    def ask(self,prompt,image_path=None,allow_fallback=True,max_tokens=None):
        primary=self.primary_provider()
        if primary and primary != "local" and not self.available().get(primary):
            raise ProviderError(f"{primary.title()} is ALICE's selected brain, but no API key is configured. Open Brain Setup.")
        errors=[]; order=self._order() if allow_fallback or getattr(self, "openrouter_free_only", False) else ([self.primary_provider()] if self.primary_provider() else [])
        for p in order:
            try: return self._call_one(p,prompt,image_path,max_tokens)
            except Exception as e:
                # _call_one already converts its terminal provider exception to
                # a safe, actionable ProviderError. Preserve that diagnosis.
                errors.append(str(e) if isinstance(e,ProviderError) else self._clean_provider_error(p,e))
        if not order:
            status=self.local_status()
            raise ProviderError(
                f"ALICE is in local-only brain mode; cloud AI keys are not used. "
                f"Start Ollama and make the configured model '{status.get('model', self.local_model)}' available, "
                "then retry."
            )
        if primary and primary != "local":
            raise ProviderError(f"{primary.title()} is ALICE's selected brain, but the request did not complete. " + (" | ".join(errors[:3]) if errors else "Check provider setup and quota."))
        raise ProviderError("No local AI provider succeeded. Start Ollama and install the configured local model. "+(" | ".join(errors[:3]) if errors else ""))

    def ask_fast(self, prompt, image_path=None, max_tokens=None):
        """Use an installed small local model for routine, read-only chat."""
        if self._runtime_mode() == "gemini_primary":
            return self.ask(prompt, image_path=image_path, allow_fallback=False,
                            max_tokens=min(int(max_tokens or 48), 80))
        if self._runtime_mode() != "local_required":
            raise ProviderError("Fast chat is available only through ALICE's local model route.")
        if not self.local_enabled:
            raise ProviderError("Local AI is disabled. Enable ALICE's local brain in its runtime configuration first.")
        if image_path:
            return self.ask_vision(prompt, image_path=image_path, max_tokens=max_tokens)
        preferred=str(os.getenv("ALICE_LOCAL_FAST_MODEL",self.local_fast_model) or "").strip()
        if not preferred or preferred == self.local_model:
            return self.ask(prompt,image_path=image_path,allow_fallback=False,max_tokens=max_tokens)
        status=self.local_status()
        if not status.get("reachable") or preferred not in status.get("models",[]):
            return self.ask(prompt,image_path=image_path,allow_fallback=False,max_tokens=max_tokens)
        started=time.monotonic()
        try:
            result=self._chat(
                self._openai_client(self.local_base,os.getenv("LOCAL_AI_API_KEY","local")),
                preferred,prompt,image_path,max_tokens=self._safe_max_tokens(prompt,max_tokens),
                keep_alive=os.getenv("ALICE_LOCAL_MODEL_KEEP_ALIVE","20m"),
            )
            if not str(result or "").strip():
                raise ProviderError("Fast local chat model returned an empty response")
            self._active_provider="local"
            self._record_success("local",time.monotonic()-started)
            return result
        except Exception as exc:
            self._record_failure("local","fast_chat_failed:"+type(exc).__name__)
            return self.ask(prompt,image_path=image_path,allow_fallback=False,max_tokens=max_tokens)

    def _gemini_client(self, api_key=None):
        token=str(api_key or os.getenv("GEMINI_API_KEY", "") or "").strip()
        if not token:
            raise ProviderError("Gemini is ALICE's primary brain, but no API key is configured. Open Brain Setup and save GEMINI_API_KEY locally.")
        client=getattr(self,"_gemini_client_obj",None)
        if client is None:
            try:
                from google import genai
                from google.genai import types
            except ImportError as exc:
                raise ProviderError("Gemini support is not installed. Install ALICE's requirements, including google-genai.") from exc
            timeout_ms=int(os.getenv("GEMINI_TIMEOUT_MS","45000"))
            timeout_ms=max(5000,min(timeout_ms,120000))
            client=genai.Client(api_key=token,http_options=types.HttpOptions(timeout=timeout_ms))
            self._gemini_client_obj=client
        return client

    @staticmethod
    def _gemini_contents(prompt, image_path=None):
        if not image_path:
            return str(prompt)
        from google.genai import types
        path=Path(image_path)
        return [str(prompt),types.Part.from_bytes(data=path.read_bytes(),
                mime_type=mimetypes.guess_type(path.name)[0] or "image/png")]

    def _ask_gemini(self,prompt,image_path=None,max_tokens=None,model_name=None):
        from google.genai import types
        client=self._gemini_client()
        model=str(model_name or os.getenv("GEMINI_MODEL",self.gemini_model) or "gemini-3.8-flash").strip()
        self.gemini_model=model
        budget=self._safe_max_tokens(prompt,max_tokens)
        response=self._gemini_request_with_retry(lambda: client.models.generate_content(
            model=model,
            contents=self._gemini_contents(prompt,image_path),
            config=types.GenerateContentConfig(temperature=0.2,max_output_tokens=budget)))
        result=getattr(response,"text",None)
        if not isinstance(result,str) or not result.strip():
            raise ProviderError("Gemini returned no text. The request may have been blocked or the response was malformed.")
        return result.strip()

    def _stream_gemini(self,prompt,image_path=None,max_tokens=None,cancel_event=None):
        if cancel_event is not None and cancel_event.is_set():
            return
        from google.genai import types
        client=self._gemini_client()
        model=str(os.getenv("GEMINI_MODEL",self.gemini_model) or "gemini-3.8-flash").strip()
        contents=self._gemini_contents(prompt,image_path)
        config=types.GenerateContentConfig(temperature=0.2,
            max_output_tokens=self._safe_max_tokens(prompt,max_tokens))
        for attempt in range(2):
            emitted=False
            try:
                stream=client.models.generate_content_stream(model=model,contents=contents,config=config)
                for chunk in stream:
                    if cancel_event is not None and cancel_event.is_set():
                        return
                    piece=getattr(chunk,"text",None)
                    if isinstance(piece,str) and piece:
                        emitted=True
                        yield piece
                if not emitted:
                    raise ProviderError("Gemini returned an empty stream.")
                return
            except Exception as exc:
                if emitted or attempt or not self._is_gemini_transient_server_error(exc):
                    raise
                time.sleep(0.6)

    def test_gemini_connection(self, *, api_key=None, model=None):
        """Perform one explicit short test; evidence excludes key and response."""
        token=str(api_key or os.getenv("GEMINI_API_KEY", "") or "").strip()
        if not token:
            raise ProviderError("Gemini is not configured. Save a key locally in Brain Setup first.")
        selected=str(model or self.gemini_model or "gemini-3.8-flash").strip()
        if not selected or len(selected)>120 or "\n" in selected or "\r" in selected:
            raise ProviderError("The configured Gemini model ID is invalid.")
        started=time.monotonic()
        try:
            answer=self._ask_gemini("Reply with exactly: ALICE Gemini connection test",max_tokens=64,model_name=selected)
            if not str(answer or "").strip():
                raise ProviderError("Gemini returned an empty connection-test response.")
            self._record_success("gemini",time.monotonic()-started)
            return {"ok":True,"provider":"gemini","model":selected,
                    "elapsed_seconds":round(time.monotonic()-started,2)}
        except Exception as exc:
            self._record_failure("gemini",exc)
            raise ProviderError(self._clean_provider_error("gemini",exc)) from None
        status=self.local_status()
        if not status.get("reachable") or preferred not in status.get("models",[]):
            return self.ask(prompt,image_path=image_path,allow_fallback=False,max_tokens=max_tokens)
        started=time.monotonic()
        try:
            result=self._chat(
                self._openai_client(self.local_base,os.getenv("LOCAL_AI_API_KEY","local")),
                preferred,prompt,image_path,max_tokens=self._safe_max_tokens(prompt,max_tokens),
                keep_alive=os.getenv("ALICE_LOCAL_MODEL_KEEP_ALIVE","20m"),
            )
            if not str(result or "").strip():
                raise ProviderError("Fast local chat model returned an empty response")
            self._active_provider="local"
            self._record_success("local",time.monotonic()-started)
            return result
        except Exception as exc:
            self._record_failure("local","fast_chat_failed:"+type(exc).__name__)
            return self.ask(prompt,image_path=image_path,allow_fallback=False,max_tokens=max_tokens)

    def ask_vision(self, prompt, image_path, max_tokens=None):
        """Use an explicitly configured local multimodal model for image input.

        A text-only primary model must not be treated as a vision model. Keep
        screenshot/media analysis local and fail clearly if its dedicated model
        is absent rather than silently trying an unrelated route.
        """
        primary=self.primary_provider()
        if primary and primary != "local":
            if not self.available().get(primary):
                raise ProviderError(f"{primary.title()} is selected but not configured. Open Brain Setup first.")
            return self._call_one(primary,prompt,image_path,max_tokens)
        if self._runtime_mode() != "local_required":
            raise ProviderError("Choose a configured provider before analyzing images.")
        if not self.local_enabled:
            raise ProviderError("Local AI is disabled. Enable ALICE's local brain before analyzing images.")
        vision_model = str(os.getenv("ALICE_LOCAL_VISION_MODEL", "")).strip()
        if not vision_model:
            raise ProviderError(
                "No local vision model is configured. Set ALICE_LOCAL_VISION_MODEL to an installed "
                "Ollama model with image-input support; ALICE will not guess that its text model can see images."
            )
        status = self.local_status()
        if not status.get("reachable") or vision_model not in status.get("models", []):
            raise ProviderError(
                f"Configured local vision model '{vision_model}' is not installed/reachable. "
                "Install it in Ollama and set ALICE_LOCAL_VISION_MODEL to its exact name."
            )
        if not image_path:
            raise ValueError("image_path is required for local vision")
        started = time.monotonic()
        try:
            result = self._chat(
                self._openai_client(self.local_base, os.getenv("LOCAL_AI_API_KEY", "local")),
                vision_model, prompt, image_path,
                max_tokens=self._safe_max_tokens(prompt, max_tokens),
                keep_alive=os.getenv("ALICE_LOCAL_MODEL_KEEP_ALIVE", "20m"),
            )
            if not str(result or "").strip():
                raise ProviderError("Local vision model returned an empty response")
            self._active_provider = "local"
            self._record_success("local_vision", time.monotonic() - started)
            return result
        except Exception as exc:
            self._record_failure("local_vision", type(exc).__name__)
            raise

    def ask_fast_stream(self, prompt, image_path=None, max_tokens=None, cancel_event=None):
        """Stream routine chat from the small on-device model when available."""
        if cancel_event is not None and cancel_event.is_set():
            return
        if self._runtime_mode() == "gemini_primary":
            yield from self.ask_stream(prompt,image_path=image_path,allow_fallback=False,
                max_tokens=min(int(max_tokens or 48),80),cancel_event=cancel_event)
            return
        if cancel_event is not None and cancel_event.is_set():
            return
        if self._runtime_mode() != "local_required":
            raise ProviderError("Fast chat is available only through ALICE's local model route.")
        if not self.local_enabled:
            raise ProviderError("Local AI is disabled. Enable ALICE's local brain in its runtime configuration first.")
        if image_path:
            yield self.ask_vision(prompt, image_path=image_path, max_tokens=max_tokens)
            return
        preferred=str(os.getenv("ALICE_LOCAL_FAST_MODEL",self.local_fast_model) or "").strip()
        status=self.local_status() if preferred and preferred != self.local_model else {}
        if not preferred or preferred == self.local_model or not status.get("reachable") or preferred not in status.get("models",[]):
            yield from self.ask_stream(prompt,image_path=image_path,allow_fallback=False,
                                       max_tokens=max_tokens,cancel_event=cancel_event)
            return
        budget=self._safe_max_tokens(prompt,max_tokens)
        emitted=False
        started=time.monotonic()
        try:
            for piece in self._stream_openai_compatible(
                    "local",prompt,image_path,budget,cancel_event,model_name=preferred):
                if str(piece or ""):
                    emitted=True
                    yield str(piece)
            if not emitted:
                raise ProviderError("Fast local chat model returned an empty stream")
            self._active_provider="local"
            self._record_success("local",time.monotonic()-started)
        except Exception:
            self._record_failure("local","fast_stream_failed")
            if emitted:
                raise
            yield from self.ask_stream(prompt,image_path=image_path,allow_fallback=False,
                                       max_tokens=max_tokens,cancel_event=cancel_event)

    def ask_json(self, prompt, schema, image_path=None, max_tokens=768):
        """Require one schema-constrained JSON object from the on-PC model.

        Planning callers validate the resulting fields before any execution.
        An unsupported structured-output endpoint is a failure, never a reason
        to switch to hosted AI or guess which of several JSON objects to use.
        """
        import json
        if self._runtime_mode() == "gemini_primary":
            client=self._gemini_client()
            from google.genai import types
            model=str(os.getenv("GEMINI_MODEL",self.gemini_model) or "gemini-3.8-flash").strip()
            try:
                response=client.models.generate_content(model=model,
                    contents=self._gemini_contents(prompt,image_path),
                    config=types.GenerateContentConfig(temperature=0,
                        max_output_tokens=self._safe_max_tokens(prompt,max_tokens),
                        response_mime_type="application/json",response_json_schema=schema))
                result=json.loads(str(getattr(response,"text","") or ""))
                if not isinstance(result,dict):
                    raise ValueError("Expected a JSON object")
                self._active_provider="gemini"
                return result
            except Exception as exc:
                self._record_failure("gemini",exc)
                raise ProviderError("Gemini structured planning failed ("+type(exc).__name__+"). No tools were executed.") from None
        primary=self.primary_provider()
        if primary and primary not in {"local", "gemini"}:
            key_name,model_name,base=self._HOSTED_CONFIG[primary]
            token=str(os.getenv(key_name,"") or "").strip()
            if not token: raise ProviderError(f"{primary.title()} is selected but has no locally configured API key.")
            model=str(os.getenv(model_name,"") or "").strip()
            if primary == "anthropic":
                result=self._anthropic_json(prompt,schema,image_path,model,max_tokens)
            else:
                client=self._openai_client(base,token)
                content=prompt
                if image_path:
                    content=[{"type":"text","text":prompt},{"type":"image_url","image_url":{"url":self._data_url(image_path)}}]
                try:
                    response=client.chat.completions.create(
                        model=model,messages=[{"role":"system","content":"Return exactly one JSON object matching the supplied schema. Do not describe or pretend to execute tools."},{"role":"user","content":content}],
                        response_format={"type":"json_schema","json_schema":{"name":"alice_tool_plan","strict":True,"schema":schema}},
                        temperature=0,max_tokens=self._safe_max_tokens(prompt,max_tokens))
                    result=json.loads(response.choices[0].message.content or "")
                    if not isinstance(result,dict): raise ValueError("Expected a JSON object")
                except Exception as exc:
                    self._record_failure(primary,exc)
                    raise ProviderError(f"{primary.title()} structured planning failed ({type(exc).__name__}). No tools were executed.") from None
            self._active_provider=primary
            return result
        from urllib.parse import urlparse
        endpoint = urlparse(self.local_base)
        if (endpoint.scheme not in {"http", "https"}
                or endpoint.hostname not in {"localhost", "127.0.0.1", "::1"}
                or endpoint.username or endpoint.password or ":cloud" in self.local_model.lower()):
            raise ProviderError("Structured planning requires an on-PC local model endpoint.")
        if "local" not in self._order():
            raise ProviderError("The configured local model is unavailable for structured planning.")
        content = prompt
        if image_path:
            content = [{"type": "text", "text": prompt},
                       {"type": "image_url", "image_url": {"url": self._data_url(image_path)}}]
        started = time.monotonic()
        try:
            client = self._openai_client(self.local_base, "local")
            response = client.chat.completions.create(
                model=self.local_model,
                messages=[{"role": "system", "content": "Return exactly one JSON object matching the supplied schema. Do not describe or pretend to execute tools."},
                          {"role": "user", "content": content}],
                response_format={"type": "json_schema", "json_schema": {"name": "alice_tool_plan", "schema": schema}},
                temperature=0, max_tokens=self._safe_max_tokens(prompt, max_tokens),
                extra_body={"keep_alive": os.getenv("ALICE_LOCAL_MODEL_KEEP_ALIVE","20m")},
            )
            choice = response.choices[0]
            if getattr(choice, "finish_reason", None) == "length":
                raise ValueError("Truncated structured plan")
            result = json.loads(choice.message.content or "")
            if not isinstance(result, dict):
                raise ValueError("Expected a JSON object")
            self._active_provider = "local"
            self._record_success("local", time.monotonic() - started)
            return result
        except Exception as exc:
            self._record_failure("local", "structured_output_failed:" + type(exc).__name__)
            raise ProviderError("Local structured planning failed (" + type(exc).__name__ + "). No tools were executed by this request.") from None

    @staticmethod
    def _gemini_schema(schema):
        """Remove local registry metadata while preserving the JSON Schema contract."""
        if isinstance(schema,dict):
            return {key:Router._gemini_schema(value) for key,value in schema.items()
                    if key not in {"source","title","additionalProperties"}}
        if isinstance(schema,list):
            return [Router._gemini_schema(value) for value in schema]
        return schema

    def ask_plan_with_tools(self,prompt,selected,image_path=None,max_tokens=768):
        """Ask Gemini for native function calls; ALICE still validates and executes.

        This method only returns proposals. The planner's existing allowlist,
        argument binding, policy, executor, confirmation, and postcondition gates
        remain authoritative. Tool results return in the next bounded planning
        prompt as observed ALICE state.
        """
        client=self._gemini_client()
        from google.genai import types
        declarations=[]
        for name,info in sorted(selected.items()):
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}",str(name)):
                continue
            schema=info.get("input_schema") or {"type":"object","properties":{},"additionalProperties":False}
            declarations.append(types.FunctionDeclaration(
                name=str(name),description=str(info.get("description") or name)[:1024],
                parameters_json_schema=self._gemini_schema(schema)))
        declarations.append(types.FunctionDeclaration(
            name="finish_plan",description="Finish planning without proposing any action. Use only when the task is already complete or no ALICE tool is needed.",
            parameters_json_schema={"type":"object","properties":{
                "goal":{"type":"string"},"done":{"type":"boolean"}},
                "required":["goal","done"],"additionalProperties":False}))
        model=str(os.getenv("GEMINI_MODEL",self.gemini_model) or "gemini-3.8-flash").strip()
        try:
            response=client.models.generate_content(model=model,
                contents=self._gemini_contents(prompt,image_path),
                config=types.GenerateContentConfig(temperature=0,
                    max_output_tokens=self._safe_max_tokens(prompt,max_tokens),
                    tools=[types.Tool(function_declarations=declarations)],
                    tool_config=types.ToolConfig(function_calling_config=
                        types.FunctionCallingConfig(mode="AUTO")),
                    automatic_function_calling={"disable":True}))
            parts=[]
            candidates=getattr(response,"candidates",None) or []
            if candidates:
                content=getattr(candidates[0],"content",None)
                parts=getattr(content,"parts",None) or []
            calls=[]
            for part in parts:
                call=getattr(part,"function_call",None)
                if call is not None:
                    name=str(getattr(call,"name","") or "")
                    args=getattr(call,"args",{}) or {}
                    if not isinstance(args,dict):
                        try: args=dict(args)
                        except Exception: args=None
                    if args is None or (name!="finish_plan" and name not in selected):
                        raise ProviderError("Gemini proposed a malformed or unregistered tool call; ALICE did not execute it.")
                    calls.append((name,args))
            if calls:
                finishes=[args for name,args in calls if name=="finish_plan"]
                actions=[{"tool":name,"args":args} for name,args in calls if name!="finish_plan"]
                if finishes and (len(finishes)!=1 or actions):
                    raise ProviderError("Gemini returned a conflicting plan; ALICE did not execute it.")
                if finishes:
                    args=finishes[0]
                    result={"goal":str(args.get("goal", "")),"done":args.get("done"),"steps":[]}
                else:
                    result={"goal":"","done":False,"steps":actions}
                self._active_provider="gemini"
                return result
            # Some supported model configurations return constrained JSON text
            # instead of a function call. Planner validation still gates it.
            import json
            text=str(getattr(response,"text","") or "").strip()
            if text:
                result=json.loads(text)
                if isinstance(result,dict):
                    self._active_provider="gemini"
                    return result
            raise ProviderError("Gemini returned no structured tool proposal; no tools were executed.")
        except Exception as exc:
            self._record_failure("gemini",exc)
            if isinstance(exc,ProviderError):
                raise
            raise ProviderError("Gemini tool planning failed ("+type(exc).__name__+"). No tools were executed.") from None

    def _stream_openai_compatible(self,p,prompt,image_path=None,max_tokens=None,cancel_event=None,model_name=None):
        # Cancellation must be honored before opening a network connection or
        # allocating a provider stream, not only after the first token arrives.
        if cancel_event is not None and cancel_event.is_set():
            return
        if p == "local":
            client=self._openai_client(self.local_base,os.getenv("LOCAL_AI_API_KEY","local")); model=model_name or self.local_model
        else:
            if p not in self._HOSTED_CONFIG: raise ProviderError(f"Provider '{p}' is not supported.")
            key_name,model_name_env,base=self._HOSTED_CONFIG[p]
            token=str(os.getenv(key_name,"") or "").strip()
            if not token: raise ProviderError(f"{p.title()} has no locally configured API key.")
            if p == "anthropic":
                yield from self._stream_anthropic(prompt,image_path,max_tokens,cancel_event)
                return
            client=self._openai_client(base,token)
            model=model_name or str(os.getenv(model_name_env,"") or "").strip()
        content=prompt
        if image_path:
            content=[{"type":"text","text":prompt},
                     {"type":"image_url","image_url":{"url":self._data_url(image_path)}}]
        kwargs={"model":model,"messages":[{"role":"user","content":content}],"temperature":0.1,"stream":True}
        if p == "local": kwargs["extra_body"]={"keep_alive":os.getenv("ALICE_LOCAL_MODEL_KEEP_ALIVE","20m")}
        if max_tokens is not None: kwargs["max_tokens"]=int(max_tokens)
        stream=client.chat.completions.create(**kwargs)
        try:
            for chunk in stream:
                if cancel_event is not None and cancel_event.is_set(): break
                choices=getattr(chunk,"choices",None) or []
                if not choices: continue
                delta=getattr(choices[0],"delta",None)
                piece=getattr(delta,"content",None) if delta is not None else None
                if piece: yield str(piece)
        finally:
            close=getattr(stream,"close",None)
            if callable(close):
                try: close()
                except Exception: pass

    def ask_stream(self,prompt,image_path=None,allow_fallback=True,max_tokens=None,cancel_event=None):
        """Yield streamed response text from the selected primary provider."""
        # A task cancelled before it reaches the provider must produce no
        # request, no retry, and no misleading empty-stream failure.
        if cancel_event is not None and cancel_event.is_set():
            return
        primary=self.primary_provider()
        if primary and primary != "local" and not self.available().get(primary):
            raise ProviderError(f"{primary.title()} is ALICE's selected brain, but no API key is configured. Open Brain Setup.")
        errors=[]
        order=self._order() if allow_fallback or getattr(self, "openrouter_free_only", False) else ([self.primary_provider()] if self.primary_provider() else [])
        for p in order:
            started=time.monotonic(); self._active_provider=p; chunks=[]
            budgets=self._retry_budgets(self._safe_max_tokens(prompt,max_tokens))
            try:
                for attempt,budget in enumerate(budgets):
                    try:
                        if p == "local":
                            iterator=self._stream_openai_compatible(p,prompt,image_path,budget,cancel_event)
                            for piece in iterator:
                                if not str(piece or ""):
                                    continue
                                chunks.append(str(piece)); yield str(piece)
                                if cancel_event is not None and cancel_event.is_set(): return
                        elif p == "gemini":
                            for piece in self._stream_gemini(prompt,image_path,budget,cancel_event):
                                if not str(piece or ""):
                                    continue
                                chunks.append(str(piece)); yield str(piece)
                                if cancel_event is not None and cancel_event.is_set(): return
                        else:
                            for piece in self._stream_openai_compatible(p,prompt,image_path,budget,cancel_event):
                                if not str(piece or ""): continue
                                chunks.append(str(piece)); yield str(piece)
                                if cancel_event is not None and cancel_event.is_set(): return
                        # Some gateways close a stream cleanly without returning any
                        # content. Treat that as a provider failure, not a success, so
                        # the bounded retry/fallback path can try another provider.
                        if not "".join(chunks).strip():
                            raise ProviderError(f"{p} returned an empty response")
                        self._record_success(p,time.monotonic()-started)
                        return
                    except Exception as e:
                        self._record_failure(p,e)
                        errors.append(self._clean_provider_error(p,e))
                        if chunks:
                            raise ProviderError("Streaming provider failed after partial output: "+errors[-1])
                        if self._is_budget_error(e):
                            hint=self._budget_hint(e)
                            if hint is not None and hint < budget:
                                # Streaming must honor the same provider-reported
                                # affordable budget logic as non-streaming calls.
                                # Never retry with a larger budget after a 402.
                                lowered=max(1, min(int(hint), budget - 1))
                                if lowered >= 1 and lowered not in budgets:
                                    budgets.insert(attempt + 1, lowered)
                        elif self._is_rate_limit_error(e):
                            if self._bounded_rate_retry(attempt):
                                continue
                            break
                        else:
                            break
            except Exception:
                raise
        if self._runtime_mode() == "local_required" and not order:
            status=self.local_status()
            raise ProviderError(
                f"ALICE is in local-only brain mode; cloud AI keys are not used. "
                f"Start Ollama and make the configured model '{status.get('model', self.local_model)}' available, "
                "then retry."
            )
        if primary and primary != "local":
            raise ProviderError(f"{primary.title()} is ALICE's selected brain, but streaming did not complete. "+(" | ".join(errors[:3]) if errors else "Check provider setup and quota."))
        raise ProviderError("No AI provider succeeded. "+(" | ".join(errors[:3]) if errors else "Configure an API key in .env."))

    def specialist(self,prompt,providers=None,image_path=None):
        """Keep council/specialist calls inside ALICE's local reasoning runtime."""
        return self.ask(prompt, image_path=image_path)

    def council(self,prompt,image_path=None): return self.specialist(prompt,image_path=image_path)

    def test_openrouter_connection(self, *, api_key=None, model=None):
        return self.test_hosted_connection("openrouter",api_key=api_key,model=model)

    def test_groq_connection(self, *, api_key=None, model=None):
        return self.test_hosted_connection("groq",api_key=api_key,model=model)

    def _openai_client(self,base=None,key=None,timeout=60.0):
        """Build an OpenAI-compatible client; endpoint policy belongs to its caller.

        This factory is intentionally network-agnostic. Local model callers must
        validate their endpoint with ``_is_loopback_url`` before reaching it.
        Other explicitly configured integrations may use ordinary HTTPS APIs.
        """
        from openai import OpenAI
        k=key or os.environ["OPENAI_API_KEY"]; b=base or None; cache=(b,k,float(timeout))
        if cache not in self._clients:self._clients[cache]=OpenAI(api_key=k,base_url=b,timeout=float(timeout),max_retries=0)
        return self._clients[cache]
    def _chat(self,client,model,prompt,image_path=None,max_tokens=None,keep_alive=None):
        content=prompt
        if image_path:
            content=[{"type":"text","text":prompt},
                     {"type":"image_url","image_url":{"url":self._data_url(image_path)}}]
        kwargs={"model":model,"messages":[{"role":"user","content":content}],"temperature":0.1}
        if max_tokens is not None: kwargs["max_tokens"]=int(max_tokens)
        if keep_alive is not None: kwargs["extra_body"]={"keep_alive":str(keep_alive)}
        r=client.chat.completions.create(**kwargs)
        return r.choices[0].message.content or ""
    def _hosted_chat(self, provider, prompt, image_path=None, max_tokens=None):
        key_name,model_name,base=self._HOSTED_CONFIG[provider]
        token=str(os.getenv(key_name,"") or "").strip()
        model=str(os.getenv(model_name,"") or "").strip()
        label=self._provider_label(provider)
        if not token: raise ProviderError(f"{label} has no locally configured API key.")
        if not model: raise ProviderError(f"Choose a model ID for {label} in Brain Setup.")
        if provider == "anthropic": return self._anthropic_request(prompt,image_path,model,max_tokens)
        return self._chat(self._openai_client(base,token),model,prompt,image_path,
                          max_tokens=self._safe_max_tokens(prompt,max_tokens))

    def _ask_openai(self,prompt,image_path=None,max_tokens=None): return self._hosted_chat("openai",prompt,image_path,max_tokens)
    def _ask_groq(self,prompt,image_path=None,max_tokens=None): return self._hosted_chat("groq",prompt,image_path,max_tokens)
    def _ask_openrouter(self,prompt,image_path=None,max_tokens=None): return self._hosted_chat("openrouter",prompt,image_path,max_tokens)
    def _ask_nvidia(self,prompt,image_path=None,max_tokens=None): return self._hosted_chat("nvidia",prompt,image_path,max_tokens)
    def _ask_local(self,prompt,image_path=None,max_tokens=None):
        if not self._is_loopback_url(self.local_base):
            raise ProviderError("Local inference endpoint must use localhost or a loopback IP address; remote model endpoints are disabled.")
        client=self._openai_client(self.local_base,os.getenv("LOCAL_AI_API_KEY","local"))
        return self._chat(client,self.local_model,prompt,image_path,max_tokens=max_tokens,keep_alive=os.getenv("ALICE_LOCAL_MODEL_KEEP_ALIVE","20m"))
    def _ask_anthropic(self,prompt,image_path=None,max_tokens=None): return self._hosted_chat("anthropic",prompt,image_path,max_tokens)

    def _anthropic_request(self,prompt,image_path,model,max_tokens=None):
        import json, urllib.request
        token=str(os.getenv("ANTHROPIC_API_KEY","") or "").strip()
        content=[{"type":"text","text":str(prompt)}]
        if image_path:
            path=Path(image_path); mime=mimetypes.guess_type(path.name)[0] or "image/png"
            content.append({"type":"image","source":{"type":"base64","media_type":mime,
                "data":base64.b64encode(path.read_bytes()).decode("ascii")}})
        body={"model":model,"max_tokens":self._safe_max_tokens(prompt,max_tokens),
              "temperature":0.1,"messages":[{"role":"user","content":content}]}
        req=urllib.request.Request("https://api.anthropic.com/v1/messages",
            data=json.dumps(body).encode("utf-8"),headers={"x-api-key":token,"anthropic-version":"2023-06-01",
            "content-type":"application/json"},method="POST")
        try:
            with urllib.request.urlopen(req,timeout=60) as response: data=json.loads(response.read().decode("utf-8"))
            return "".join(str(item.get("text", "")) for item in data.get("content",[]) if item.get("type")=="text")
        except Exception as exc:
            safe=str(exc).replace(token,"[redacted]")
            raise ProviderError(self._clean_provider_error("anthropic",safe)) from None

    def _anthropic_json(self,prompt,schema,image_path,model,max_tokens):
        import json
        full=(str(prompt)+"\n\nReturn exactly one JSON object conforming to this JSON Schema. Do not include markdown or prose.\n"+
              json.dumps(schema,separators=(",",":")))
        raw=self._anthropic_request(full,image_path,model,max_tokens)
        try:
            start=raw.find("{"); end=raw.rfind("}")
            result=json.loads(raw[start:end+1]) if start>=0 and end>=start else None
            if not isinstance(result,dict): raise ValueError("Expected JSON object")
            return result
        except Exception as exc:
            raise ProviderError(f"Anthropic structured planning returned invalid JSON ({type(exc).__name__}). No tools were executed.") from None

    def _stream_anthropic(self,prompt,image_path,max_tokens,cancel_event):
        # Anthropic stream events are parsed incrementally. A cancelled request
        # closes the response immediately; no silent provider switch occurs.
        import json, urllib.request
        if cancel_event is not None and cancel_event.is_set(): return
        token=str(os.getenv("ANTHROPIC_API_KEY","") or "").strip()
        model=str(os.getenv("ANTHROPIC_MODEL","") or "").strip()
        if not token or not model: raise ProviderError("Anthropic key and model must be configured in Brain Setup.")
        content=[{"type":"text","text":str(prompt)}]
        if image_path:
            path=Path(image_path); mime=mimetypes.guess_type(path.name)[0] or "image/png"
            content.append({"type":"image","source":{"type":"base64","media_type":mime,"data":base64.b64encode(path.read_bytes()).decode("ascii")}})
        body={"model":model,"max_tokens":self._safe_max_tokens(prompt,max_tokens),"temperature":0.1,
              "stream":True,"messages":[{"role":"user","content":content}]}
        req=urllib.request.Request("https://api.anthropic.com/v1/messages",data=json.dumps(body).encode(),
              headers={"x-api-key":token,"anthropic-version":"2023-06-01","content-type":"application/json"},method="POST")
        try:
            with urllib.request.urlopen(req,timeout=60) as response:
                for raw in response:
                    if cancel_event is not None and cancel_event.is_set(): return
                    line=raw.decode("utf-8","replace").strip()
                    if not line.startswith("data:"): continue
                    try: event=json.loads(line[5:].strip())
                    except Exception: continue
                    if event.get("type")=="content_block_delta":
                        delta=event.get("delta") or {}
                        if delta.get("type")=="text_delta" and delta.get("text"): yield str(delta["text"])
        except Exception as exc:
            safe=str(exc).replace(token,"[redacted]")
            raise ProviderError(self._clean_provider_error("anthropic",safe)) from None

    def test_hosted_connection(self, provider, *, api_key=None, model=None):
        name=str(provider or "").strip().lower()
        if name not in self._HOSTED_CONFIG: raise ProviderError("Choose a supported hosted provider.")
        key_name,model_name,_base=self._HOSTED_CONFIG[name]
        token=str(api_key or os.getenv(key_name,"") or "").strip()
        selected=str(model or os.getenv(model_name,"") or "").strip()
        if not token or not selected: raise ProviderError(f"Enter the {self._provider_label(name)} API key and model first.")
        started=time.monotonic()
        try:
            previous=os.environ.get(key_name); previous_model=os.environ.get(model_name)
            os.environ[key_name]=token; os.environ[model_name]=selected
            answer=self._hosted_chat(name,"Reply with exactly: ALICE connection test",max_tokens=64)
            if not str(answer or "").strip(): raise ProviderError(f"{name.title()} returned an empty response.")
            self._record_success(name,time.monotonic()-started)
            return {"ok":True,"provider":name,"model":selected,"elapsed_seconds":round(time.monotonic()-started,2)}
        except Exception as exc:
            safe=str(exc).replace(token,"[redacted]")
            self._record_failure(name,safe)
            raise ProviderError(self._clean_provider_error(name,safe)) from None
        finally:
            if previous is None: os.environ.pop(key_name,None)
            else: os.environ[key_name]=previous
            if previous_model is None: os.environ.pop(model_name,None)
            else: os.environ[model_name]=previous_model
