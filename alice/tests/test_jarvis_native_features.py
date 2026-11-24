import hashlib
import json
from pathlib import Path

import pytest

from alice.computer.system_tools import (WindowsHardware, verify_brightness_change_postcondition,
                                         verify_volume_change_postcondition)
from alice.multimodal.camera import CameraCapture
from alice.weather import OpenMeteoWeather, verify_weather_lookup_postcondition
from alice.integrations.public_ip import PublicIPLookup, verify_public_ip_postcondition


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.url = "https://geocoding-api.open-meteo.com/v1/search"

    def json(self):
        return self.payload


def test_open_meteo_resolves_location_and_returns_current_conditions():
    responses = iter([
        FakeResponse({"results": [{"name": "Bengaluru", "country": "India", "latitude": 12.97,
                                   "longitude": 77.59, "timezone": "Asia/Kolkata"}]}),
        FakeResponse({"current": {"time": "2026-10-14T12:00", "temperature_2m": 28.2,
                                   "relative_humidity_2m": 45, "is_day": 1,
                                   "precipitation": 0.0, "weather_code": 1, "wind_speed_10m": 9.4}}),
    ])
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return next(responses)

    result = OpenMeteoWeather(get=get).lookup("Bengaluru")

    assert result["ok"] is True
    assert result["location"] == "Bengaluru, India"
    assert result["temperature_c"] == 28.2
    assert result["conditions"] == "Mainly clear"
    assert verify_weather_lookup_postcondition({}, result).ok is True
    assert len(calls) == 2
    assert all(call[1]["timeout"] <= 10 and call[1]["allow_redirects"] is False for call in calls)


def test_weather_fails_closed_for_empty_or_unavailable_locations():
    with pytest.raises(ValueError, match="location"):
        OpenMeteoWeather(get=lambda *_a, **_k: None).lookup("  ")

    result = OpenMeteoWeather(get=lambda *_a, **_k: FakeResponse({"results": []})).lookup("No Such Place")
    assert result == {"ok": False, "error": "No matching location was found.", "source": "open-meteo"}


def test_public_ip_lookup_validates_response_and_does_not_persist():
    class Response:
        status_code = 200
        def json(self): return {"ip": "203.0.113.27"}

    result = PublicIPLookup(get=lambda *_a, **_k: Response()).lookup()

    assert result["ok"] is True
    assert result["version"] == 4
    assert result["persisted"] is False
    assert verify_public_ip_postcondition({}, result).ok is True


def test_public_ip_lookup_rejects_non_ip_response():
    class Response:
        status_code = 200
        def json(self): return {"ip": "not-an-ip"}

    result = PublicIPLookup(get=lambda *_a, **_k: Response()).lookup()
    assert result["ok"] is False
    assert result["persisted"] is False


def test_battery_status_reads_windows_fields_without_psutil():
    hardware = WindowsHardware(platform_name="Windows", power_reader=lambda: {
        "ACLineStatus": 1, "BatteryFlag": 8, "BatteryLifePercent": 67,
        "SystemStatusFlag": 0, "BatteryLifeTime": 3600, "BatteryFullLifeTime": 7200,
    })

    result = hardware.battery_status()

    assert result["ok"] is True
    assert result["percent"] == 67
    assert result["ac_online"] is True
    assert result["charging"] is True
    assert result["seconds_remaining"] == 3600


def test_brightness_set_requires_exact_readback_and_valid_range():
    hardware = WindowsHardware(platform_name="Windows", powershell_runner=lambda _script: json.dumps({
        "ok": True, "requested": 70, "levels": [70, 70], "monitor_count": 2, "verified": True,
    }))

    assert hardware.set_brightness(70)["verified"] is True
    with pytest.raises(ValueError, match="0 to 100"):
        hardware.set_brightness(101)


def test_brightness_set_does_not_claim_success_when_readback_mismatches():
    hardware = WindowsHardware(platform_name="Windows", powershell_runner=lambda _script: json.dumps({
        "ok": False, "requested": 70, "levels": [50], "monitor_count": 1, "verified": False,
    }))

    result = hardware.set_brightness(70)
    assert result["ok"] is False
    assert result["levels"] == [50]


def test_brightness_postcondition_uses_a_fresh_observer_read():
    class Observer:
        calls = 0
        def brightness_status(self):
            self.calls += 1
            return {"ok": True, "levels": [60, 60]}
        @staticmethod
        def _percentage(value): return WindowsHardware._percentage(value)

    hardware = Observer()
    result = verify_brightness_change_postcondition({"percent": 60},
        {"ok": True, "verified": True}, hardware)

    assert result.ok is True
    assert hardware.calls == 1


def test_volume_postcondition_fails_when_fresh_readback_differs():
    class Observer:
        def volume_status(self): return {"ok": True, "percent": 40}
        @staticmethod
        def _percentage(value): return WindowsHardware._percentage(value)

    result = verify_volume_change_postcondition({"percent": 42},
        {"ok": True, "verified": True}, Observer())
    assert result.ok is False
    assert result.evidence["observed"] is False


class FakeVolume:
    def __init__(self, value=0.4):
        self.value = value

    def GetMasterVolumeLevelScalar(self):
        return self.value

    def SetMasterVolumeLevelScalar(self, value, _event_context):
        self.value = value


def test_volume_set_verifies_scalar_readback():
    endpoint = FakeVolume()
    hardware = WindowsHardware(platform_name="Windows", volume_endpoint_factory=lambda: endpoint)

    result = hardware.set_volume(72)

    assert result["ok"] is True
    assert result["verified"] is True
    assert result["percent"] == 72
    assert endpoint.value == pytest.approx(0.72)


def test_camera_capture_requires_confirmation_and_verifies_saved_bytes(tmp_path):
    class FakeCapture:
        def isOpened(self):
            return True

        def read(self):
            return True, object()

        def release(self):
            pass

    class FakeCV2:
        def VideoCapture(self, index):
            assert index == 0
            return FakeCapture()

        def imwrite(self, path, _frame):
            Path(path).write_bytes(b"fake-camera-frame")
            return True

    camera = CameraCapture(tmp_path, cv2_module=FakeCV2())
    with pytest.raises(PermissionError, match="explicit confirmation"):
        camera.capture()

    result = camera.capture(confirm_camera_access=True)

    captured = Path(result["path"])
    assert result["ok"] is True
    assert captured.is_relative_to(tmp_path / "alice_workspace" / "captures" / "camera")
    assert result["sha256"] == hashlib.sha256(captured.read_bytes()).hexdigest()


def test_camera_capture_rejects_invalid_device_index(tmp_path):
    camera = CameraCapture(tmp_path, cv2_module=object())
    with pytest.raises(ValueError, match="camera_index"):
        camera.capture(camera_index=99, confirm_camera_access=True)


def test_devour_license_scanner_finds_wrapped_gpl_license(tmp_path):
    from alice.gluttony.assimilation import AssimilationEngine, license_requires_review

    source = tmp_path / "staged"
    nested = source / "jarvis-ai-assistant-main"
    nested.mkdir(parents=True)
    (nested / "LICENSE").write_text(
        "GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007\n", encoding="utf-8"
    )

    result = AssimilationEngine(tmp_path)._license(source)

    assert result["kind"] == "GPL-3.0"
    assert result["files"] == ["jarvis-ai-assistant-main/LICENSE"]
    assert license_requires_review(result["kind"]) is True


def test_camera_capture_postcondition_hashes_the_saved_frame(tmp_path):
    from alice.multimodal.camera import verify_camera_capture_postcondition

    class FakeCapture:
        def isOpened(self): return True
        def read(self): return True, object()
        def release(self): pass

    class FakeCV2:
        def VideoCapture(self, _index): return FakeCapture()
        def imwrite(self, path, _frame):
            Path(path).write_bytes(b"verified-frame")
            return True

    result = CameraCapture(tmp_path, cv2_module=FakeCV2()).capture(confirm_camera_access=True)
    verified = verify_camera_capture_postcondition({}, result, tmp_path)
    assert verified.ok is True
    assert verified.evidence["observed"] is True


def test_jarvis_native_features_are_registered_with_action_risks():
    source = Path(__file__).resolve().parents[1] / "ui" / "app.py"
    app = source.read_text(encoding="utf-8")

    assert 't.add("weather_lookup"' in app
    assert 't.add("public_ip_lookup"' in app
    assert 't.add("battery_status"' in app
    assert 't.add("set_display_brightness"' in app
    assert 't.add("set_system_volume"' in app
    assert 't.add("capture_camera_image"' in app
    assert '"external"' in app[app.index('t.add("capture_camera_image"'):app.index('t.add("capture_camera_image"') + 300]
    assert 't.postconditions.register("set_display_brightness"' in app
    assert 't.postconditions.register("set_system_volume"' in app
    for name in ("weather_lookup", "public_ip_lookup", "set_display_brightness", "set_system_volume", "capture_camera_image"):
        assert app.count(f't.postconditions.register("{name}"') == 1
