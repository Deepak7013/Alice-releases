"""Bind local model artifact verification directly to admission policy."""
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Mapping, Sequence
import hashlib
import json
from pathlib import Path
from .model_manifest import LocalModelVerification, verify_local_model_manifest
from .model_admission import LocalVoiceModelAdmissionGate, ModelAdmission

@dataclass(frozen=True)
class ModelAdmissionReport:
    admitted: bool
    verification: LocalModelVerification
    decision: ModelAdmission
    reason: str
    receipt_digest: str | None = None
    receipt_json: str | None = None
    receipt_json: str | None = None


def verify_and_admit_local_model(model_root: str | Path, artifacts: Sequence[Mapping[str, object]], *,
                                 model_name: object, model_format: object, local_owned: object,
                                 offline: object, license_reviewed: object,
                                 runtime_ready: object) -> ModelAdmissionReport:
    """Verify actual files, then pass that result—not caller input—to policy.

    The bridge does not load or execute model code. `runtime_ready` must come
    from a separate real runtime health check; this function does not infer it.
    """
    verification = verify_local_model_manifest(model_root, artifacts)
    decision = LocalVoiceModelAdmissionGate().evaluate(
        model_name=model_name, model_format=model_format,
        local_owned=local_owned, offline=offline,
        manifest_verified=verification.ok,
        license_reviewed=license_reviewed, runtime_ready=runtime_ready,
    )
    ok = verification.ok and decision.admitted
    reason = "local_model_verified_and_admitted" if ok else (verification.reason if not verification.ok else decision.reason)
    receipt = {
        "model_name": str(model_name or "").strip(),
        "model_format": str(model_format or "").strip().lower(),
        "manifest_digest": verification.manifest_digest,
        "verification_ok": verification.ok,
        "decision_admitted": decision.admitted,
        "decision_reason": decision.reason,
        "local_owned": local_owned is True,
        "offline": offline is True,
        "license_reviewed": license_reviewed is True,
        "runtime_ready": runtime_ready is True,
        "result_admitted": ok,
        "result_reason": reason,
        "artifact_results": [
            {"name": item.name, "ok": item.ok, "reason": item.reason}
            for item in verification.artifacts
        ],
    }
    receipt_json = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
    receipt_digest = hashlib.sha256(receipt_json.encode("utf-8")).hexdigest()
    return ModelAdmissionReport(ok, verification, decision, reason, receipt_digest, receipt_json)


MAX_ADMISSION_RECEIPT_BYTES = 262144

def verify_model_admission_receipt(receipt_json: object, receipt_digest: object, *,
                                   expected_admitted: object | None = None) -> tuple[bool, str]:
    """Independently verify a serialized admission receipt and its SHA-256 digest."""
    if not isinstance(receipt_json, str) or not receipt_json:
        return False, "receipt_missing"
    if len(receipt_json.encode("utf-8")) > MAX_ADMISSION_RECEIPT_BYTES:
        return False, "receipt_too_large"
    if not isinstance(receipt_digest, str) or len(receipt_digest) != 64:
        return False, "receipt_digest_invalid"
    actual = hashlib.sha256(receipt_json.encode("utf-8")).hexdigest()
    if actual != receipt_digest.lower():
        return False, "receipt_digest_mismatch"
    try:
        parsed = json.loads(receipt_json)
    except Exception:
        return False, "receipt_json_invalid"
    if not isinstance(parsed, dict):
        return False, "receipt_schema_invalid"
    required = {"model_name", "model_format", "manifest_digest", "verification_ok",
                "decision_admitted", "decision_reason", "result_admitted", "result_reason",
                "artifact_results"}
    if not required.issubset(parsed):
        return False, "receipt_schema_incomplete"
    if type(parsed.get("verification_ok")) is not bool or type(parsed.get("decision_admitted")) is not bool or type(parsed.get("result_admitted")) is not bool:
        return False, "receipt_boolean_fields_invalid"
    if parsed["result_admitted"] != (parsed["verification_ok"] and parsed["decision_admitted"]):
        return False, "receipt_outcome_inconsistent"
    if expected_admitted is not None and parsed["result_admitted"] is not expected_admitted:
        return False, "receipt_outcome_mismatch"
    artifact_results = parsed.get("artifact_results")
    if not isinstance(artifact_results, list) or len(artifact_results) > 512:
        return False, "receipt_artifact_results_invalid"
    for item in artifact_results:
        if not isinstance(item, dict):
            return False, "receipt_artifact_entry_invalid"
        if not isinstance(item.get("name"), str) or type(item.get("ok")) is not bool or not isinstance(item.get("reason"), str):
            return False, "receipt_artifact_entry_invalid"
        if len(item["name"]) > 160 or len(item["reason"]) > 128:
            return False, "receipt_artifact_entry_invalid"
    return True, "receipt_verified"
