"""One-frame camera capture with explicit consent and workspace-only output."""
from __future__ import annotations

import hashlib
import importlib
import os
import uuid
from pathlib import Path


class CameraCapture:
    def __init__(self, root, cv2_module=None):
        self.root = Path(root).resolve()
        self._cv2 = cv2_module

    def capture(self, camera_index=0, confirm_camera_access=False):
        if confirm_camera_access is not True:
            raise PermissionError("Camera access needs explicit confirmation for this capture.")
        if isinstance(camera_index, bool):
            raise ValueError("camera_index must be an integer from 0 to 10")
        try:
            index = int(camera_index)
        except (TypeError, ValueError) as exc:
            raise ValueError("camera_index must be an integer from 0 to 10") from exc
        if index < 0 or index > 10:
            raise ValueError("camera_index must be an integer from 0 to 10")
        cv2 = self._cv2
        if cv2 is None:
            try:
                cv2 = importlib.import_module("cv2")
            except Exception as exc:
                raise RuntimeError("Camera capture needs ALICE's optional OpenCV dependency; install requirements-camera.txt in ALICE's virtual environment.") from exc

        output_dir = (self.root / "alice_workspace" / "captures" / "camera").resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / f"capture_{uuid.uuid4().hex}.jpg"
        staging = target.with_suffix(".part.jpg")
        device = None
        try:
            device = cv2.VideoCapture(index)
            if not device.isOpened():
                raise RuntimeError(f"Camera {index} could not be opened.")
            ok, frame = device.read()
            if not ok or frame is None:
                raise RuntimeError("The camera opened but did not produce a frame.")
            if not cv2.imwrite(str(staging), frame) or not staging.is_file() or staging.stat().st_size == 0:
                raise RuntimeError("Camera image could not be saved and verified.")
            os.replace(staging, target)
            payload = target.read_bytes()
            return {"ok": True, "path": str(target), "size_bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(), "verified": True,
                    "camera_index": index}
        finally:
            if device is not None:
                try:
                    device.release()
                except Exception:
                    pass
            try:
                staging.unlink(missing_ok=True)
            except Exception:
                pass


def verify_camera_capture_postcondition(args, result, root=None):
    from ..execution.postconditions import PostconditionResult
    if not isinstance(result, dict) or result.get("ok") is not True:
        return PostconditionResult(False, {"observed": False}, "camera_capture_not_reported")
    path = Path(str(result.get("path", "")))
    source_root = Path(root or args.get("root", path.parents[3] if len(path.parents) > 3 else path.parent))
    capture_root = (source_root / "alice_workspace" / "captures" / "camera").resolve()
    try:
        actual = path.resolve()
        actual.relative_to(capture_root)
        data = actual.read_bytes()
    except Exception as exc:
        return PostconditionResult(False, {"observed": False, "error": str(exc)[:160]},
                                   "camera_capture_path_or_readback_invalid")
    digest = hashlib.sha256(data).hexdigest()
    ok = bool(data) and digest == result.get("sha256") and len(data) == result.get("size_bytes")
    return PostconditionResult(ok, {"observed": ok, "sha256": digest, "size_bytes": len(data)},
                               "camera_file_digest_read_back" if ok else "camera_capture_digest_mismatch")
