"""Bounded Windows battery, display-brightness and master-volume controls."""
from __future__ import annotations

import ctypes
import json
import os
import platform
import subprocess


class WindowsHardware:
    def __init__(self, *, platform_name=None, power_reader=None, powershell_runner=None,
                 volume_endpoint_factory=None):
        self.platform_name = platform_name or platform.system()
        self._power_reader = power_reader
        self._powershell_runner = powershell_runner or self._run_powershell
        self._volume_endpoint_factory = volume_endpoint_factory

    @property
    def is_windows(self):
        return str(self.platform_name).casefold() == "windows"

    @staticmethod
    def _read_system_power_status():
        if os.name != "nt":
            raise RuntimeError("Windows battery status is unavailable on this operating system.")

        class SYSTEM_POWER_STATUS(ctypes.Structure):
            _fields_ = [
                ("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                ("BatteryLifeTime", ctypes.c_uint32), ("BatteryFullLifeTime", ctypes.c_uint32),
            ]

        status = SYSTEM_POWER_STATUS()
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            raise ctypes.WinError(ctypes.get_last_error())
        return {name: getattr(status, name) for name, _kind in status._fields_}

    def battery_status(self):
        if not self.is_windows:
            return {"ok": False, "error": "Battery status is currently supported on Windows only."}
        try:
            read = self._power_reader or self._read_system_power_status
            data = read()
            percent = int(data["BatteryLifePercent"])
            line = int(data["ACLineStatus"])
            flag = int(data["BatteryFlag"])
            lifetime = int(data["BatteryLifeTime"])
            return {
                "ok": True,
                "percent": None if percent == 255 or flag & 128 else max(0, min(100, percent)),
                "ac_online": None if line == 255 else line == 1,
                "charging": None if flag == 255 else bool(flag & 8),
                "battery_present": None if flag == 255 else not bool(flag & 128),
                "seconds_remaining": None if lifetime in (0, 0xFFFFFFFF) else lifetime,
                "source": "Windows GetSystemPowerStatus",
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:240]}

    @staticmethod
    def _run_powershell(script):
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=12, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode:
            raise RuntimeError((completed.stderr or completed.stdout or "PowerShell CIM query failed.")[:300].strip())
        return completed.stdout

    def _powershell_json(self, script):
        if not self.is_windows:
            raise RuntimeError("Display brightness controls are currently supported on Windows only.")
        raw = self._powershell_runner(script)
        if isinstance(raw, dict):
            return raw
        if hasattr(raw, "stdout"):
            if int(getattr(raw, "returncode", 0)) != 0:
                raise RuntimeError((getattr(raw, "stderr", "") or "PowerShell CIM query failed.")[:300].strip())
            raw = raw.stdout
        try:
            return json.loads(str(raw).strip())
        except Exception as exc:
            raise RuntimeError("Windows brightness service returned unreadable state.") from exc

    def brightness_status(self):
        script = (
            "$levels = @(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness "
            "-ErrorAction Stop | ForEach-Object { [int]$_.CurrentBrightness }); "
            "ConvertTo-Json -InputObject $levels -Compress"
        )
        try:
            levels = self._powershell_json(script)
            if not isinstance(levels, list):
                levels = [levels]
            if not levels:
                return {"ok": False, "error": "No brightness-capable display was found."}
            values = [int(item) for item in levels]
            return {"ok": True, "levels": values, "percent": values[0], "monitor_count": len(values),
                    "source": "WMI WmiMonitorBrightness"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:240]}

    def set_brightness(self, percent):
        target = self._percentage(percent)
        script = (
            f"$target = {target}; "
            "$methods = @(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods -ErrorAction Stop); "
            "if ($methods.Count -eq 0) { throw 'No brightness-capable display was found.' }; "
            "foreach ($item in $methods) { $r = Invoke-CimMethod -InputObject $item -MethodName WmiSetBrightness "
            "-Arguments @{ Timeout = [uint32]1; Brightness = [byte]$target } -ErrorAction Stop; "
            "if ([int]$r.ReturnValue -ne 0) { throw ('Brightness control returned ' + $r.ReturnValue) } }; "
            "$levels = @((Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness -ErrorAction Stop) "
            "| ForEach-Object { [int]$_.CurrentBrightness }); "
            "$verified = ($levels.Count -gt 0 -and @($levels | Where-Object { $_ -ne $target }).Count -eq 0); "
            "[pscustomobject]@{ ok = $verified; verified = $verified; requested = $target; levels = $levels; "
            "monitor_count = $methods.Count } | ConvertTo-Json -Compress"
        )
        try:
            result = self._powershell_json(script)
            if not isinstance(result, dict):
                return {"ok": False, "verified": False, "error": "Brightness service returned no verification record."}
            result.setdefault("ok", False)
            result.setdefault("verified", False)
            return result
        except Exception as exc:
            return {"ok": False, "verified": False, "requested": target, "error": str(exc)[:240]}

    @staticmethod
    def _percentage(value):
        if isinstance(value, bool):
            raise ValueError("percentage must be a number from 0 to 100")
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("percentage must be a number from 0 to 100") from exc
        if not 0 <= parsed <= 100:
            raise ValueError("percentage must be from 0 to 100")
        return int(round(parsed))

    def _volume_endpoint(self):
        if self._volume_endpoint_factory is not None:
            return self._volume_endpoint_factory()
        if not self.is_windows:
            raise RuntimeError("Master volume controls are currently supported on Windows only.")
        try:
            from ctypes import POINTER, cast
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        except Exception as exc:
            raise RuntimeError("Master volume controls require ALICE's Windows `pycaw` dependency; install from requirements.txt.") from exc
        speaker = AudioUtilities.GetSpeakers()
        endpoint = getattr(speaker, "EndpointVolume", None)
        if endpoint is not None:
            return endpoint
        endpoint = speaker.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(endpoint, POINTER(IAudioEndpointVolume))

    def volume_status(self):
        try:
            endpoint = self._volume_endpoint()
            percent = float(endpoint.GetMasterVolumeLevelScalar()) * 100
            if not 0 <= percent <= 100:
                raise RuntimeError("Windows audio endpoint returned an invalid master-volume value.")
            return {"ok": True, "percent": int(round(percent)), "source": "Windows default audio endpoint"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:240]}

    def set_volume(self, percent):
        target = self._percentage(percent)
        try:
            endpoint = self._volume_endpoint()
            endpoint.SetMasterVolumeLevelScalar(target / 100.0, None)
            observed = int(round(float(endpoint.GetMasterVolumeLevelScalar()) * 100))
            verified = abs(observed - target) <= 1
            return {"ok": verified, "verified": verified, "requested": target, "percent": observed,
                    "source": "Windows default audio endpoint"}
        except Exception as exc:
            return {"ok": False, "verified": False, "requested": target, "error": str(exc)[:240]}


def verify_brightness_change_postcondition(args, result, hardware):
    from ..execution.postconditions import PostconditionResult
    current = hardware.brightness_status()
    levels = current.get("levels", []) if current.get("ok") else []
    try:
        expected = hardware._percentage(args.get("percent"))
    except Exception:
        expected = None
    observed = bool(levels) and expected is not None and all(int(value) == expected for value in levels)
    ok = observed and isinstance(result, dict) and result.get("ok") is True and result.get("verified") is True
    return PostconditionResult(ok, {"observed": bool(observed), "levels": levels, "requested": expected},
                               "fresh WMI brightness readback" if ok else "brightness_readback_mismatch")


def verify_volume_change_postcondition(args, result, hardware):
    from ..execution.postconditions import PostconditionResult
    current = hardware.volume_status()
    observed = current.get("percent") if current.get("ok") else None
    try:
        expected = hardware._percentage(args.get("percent"))
    except Exception:
        expected = None
    matched = observed is not None and expected is not None and abs(int(observed) - expected) <= 1
    ok = matched and isinstance(result, dict) and result.get("ok") is True and result.get("verified") is True
    return PostconditionResult(ok, {"observed": bool(matched), "percent": observed, "requested": expected},
                               "fresh Windows volume readback" if ok else "volume_readback_mismatch")
