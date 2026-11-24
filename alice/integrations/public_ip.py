"""On-demand public-IP lookup with no persistence."""
from __future__ import annotations

import ipaddress


class PublicIPLookup:
    ENDPOINT = "https://api.ipify.org"

    def __init__(self, get=None, timeout=5):
        self._get = get
        self.timeout = max(1, min(int(timeout), 8))

    def lookup(self):
        try:
            get = self._get
            if get is None:
                import requests
                get = requests.get
            response = get(self.ENDPOINT, params={"format": "json"}, timeout=self.timeout,
                           allow_redirects=False)
            if int(getattr(response, "status_code", 0)) != 200:
                return {"ok": False, "error": "Public-IP service did not return HTTP 200."}
            payload = response.json()
            value = str(payload.get("ip", "")).strip() if isinstance(payload, dict) else ""
            address = ipaddress.ip_address(value)
            return {"ok": True, "ip": str(address), "version": address.version,
                    "source": self.ENDPOINT, "persisted": False}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:200], "persisted": False}


def verify_public_ip_postcondition(_args, result):
    from ..execution.postconditions import PostconditionResult
    try:
        address = ipaddress.ip_address(result.get("ip")) if isinstance(result, dict) else None
        valid = (isinstance(result, dict) and result.get("ok") is True and address is not None
                 and result.get("source") == PublicIPLookup.ENDPOINT and result.get("persisted") is False)
    except Exception:
        address = None
        valid = False
    return PostconditionResult(valid, {"observed": valid, "ip_version": address.version if address else None},
                               "public IP validated from HTTPS service" if valid else "public_ip_not_verified")
