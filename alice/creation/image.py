from __future__ import annotations
import base64, os, tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from alice.providers.runtime_policy import RuntimePolicy

class ImageGenerationProvider:
    def generate(self, prompt: str, output_path: str, size: str = "1024x1024"):
        raise NotImplementedError

class OpenAIImageProvider(ImageGenerationProvider):
    """Optional OpenAI image adapter. Credentials remain in environment variables."""
    ALLOWED_SIZES = {"1024x1024", "1536x1024", "1024x1536", "auto"}

    def __init__(self, client=None, model=None):
        self.client=client
        self.model=model or os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")

    def generate(self, prompt, output_path, size="1024x1024"):
        prompt = str(prompt or "").strip()
        if not prompt or len(prompt) > 20000:
            raise ValueError("Image prompt must contain between 1 and 20000 characters")
        size = str(size or "1024x1024").strip().lower()
        if size not in self.ALLOWED_SIZES:
            raise ValueError("Unsupported image size")
        if RuntimePolicy.from_env().mode == "local_required":
            raise RuntimeError(
                "Image generation is not available in local-only brain mode: this build has no local image model. "
                "No cloud image API was called. Choose a local image-generation backend or explicitly change Brain mode."
            )
        if self.client is None:
            from openai import OpenAI
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            if not api_key:
                raise RuntimeError("Image generation requires OPENAI_API_KEY; ALICE has not uploaded anything")
            self.client=OpenAI(api_key=api_key)
        result=self.client.images.generate(model=self.model, prompt=prompt, size=size)
        items=getattr(result, "data", None) or []
        if not items:
            raise RuntimeError("Image provider returned an empty result")
        item=items[0]
        p=Path(output_path); p.parent.mkdir(parents=True,exist_ok=True)
        temp_path=None
        try:
            with tempfile.NamedTemporaryFile(prefix=p.name + ".", suffix=".tmp", dir=p.parent, delete=False) as stream:
                temp_path=Path(stream.name)
                if getattr(item,"b64_json",None):
                    stream.write(base64.b64decode(item.b64_json, validate=True))
                elif getattr(item,"url",None):
                    url=str(item.url)
                    parsed=urlparse(url)
                    if parsed.scheme != "https" or not parsed.netloc:
                        raise RuntimeError("Image provider returned a non-HTTPS image URL")
                    request=Request(url, headers={"User-Agent":"ALICE-image-client/1.0"})
                    with urlopen(request, timeout=30) as response:
                        content_type=response.headers.get("Content-Type", "").lower()
                        if not content_type.startswith("image/"):
                            raise RuntimeError("Image provider URL did not return an image content type")
                        payload=response.read(50 * 1024 * 1024 + 1)
                        if len(payload) > 50 * 1024 * 1024:
                            raise RuntimeError("Generated image exceeds the 50 MiB safety limit")
                        stream.write(payload)
                else:
                    raise RuntimeError("Image provider returned no image data")
                stream.flush()
                os.fsync(stream.fileno())
            if not temp_path.is_file() or temp_path.stat().st_size <= 0:
                raise RuntimeError("Image provider returned an empty image artifact")
            os.replace(temp_path, p)
            temp_path=None
            return str(p)
        finally:
            if temp_path is not None:
                try: temp_path.unlink(missing_ok=True)
                except OSError: pass
