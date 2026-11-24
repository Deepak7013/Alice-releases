"""Central safety policy for autonomous operation."""
import re

BLOCKED=re.compile(r"(?i)\b(ransomware|credential\s*steal|keylogger|malware|virus|trojan|botnet|ddos|phishing\s+kit|bypass\s+(?:auth|security|2fa)|disable\s+(?:antivirus|defender|security))\b")
CONSEQUENTIAL=re.compile(r"(?i)\b(purchase|buy|checkout|transfer|send\s+money|delete|format|factory\s+reset|publish|post|send\s+email|change\s+password|create\s+account|accept\s+terms)\b")
class SafetyPolicy:
    def inspect_request(self, request):
        if BLOCKED.search(request): return {"allowed":False,"reason":"Potentially harmful or abusive task"}
        return {"allowed":True,"needs_confirmation":bool(CONSEQUENTIAL.search(request))}
    def inspect_text(self,text):
        return not BLOCKED.search(text or "")
