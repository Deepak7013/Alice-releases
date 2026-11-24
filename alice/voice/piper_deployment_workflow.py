"""Guided preflight-first workflow for a real Piper-only diagnostic."""
from __future__ import annotations
from .piper_deployment_preflight import run_piper_deployment_preflight
from .piper_runtime_diagnostic import run_piper_runtime_diagnostic

def run_guided_piper_check(config_file, receipt_file, *, confirm_female=False,
                           preflight=run_piper_deployment_preflight,
                           runtime_diagnostic=run_piper_runtime_diagnostic,
                           platform_name=None):
    pre = preflight(config_file, platform_name=platform_name)
    result = {"preflight": pre, "runtime": None, "passed": False,
              "reason": "preflight_not_ready"}
    if not pre.get("ready_for_runtime_test"):
        return result
    if not confirm_female:
        result["reason"] = "female_profile_confirmation_required"
        return result
    runtime = runtime_diagnostic(config_file, receipt_file, confirm_female=True,
                                 platform_name=platform_name)
    result["runtime"] = runtime
    result["passed"] = bool(runtime.get("passed"))
    result["reason"] = "piper_runtime_test_passed" if result["passed"] else "piper_runtime_test_failed"
    return result
