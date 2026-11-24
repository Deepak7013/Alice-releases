"""Bounded Windows UI Automation observer for the foreground desktop window."""
from __future__ import annotations

import hashlib
import os


class WindowsUIAutomation:
    """Read visible accessibility controls and invoke one unique named button or link."""

    _CONTROL_TYPES = {"button": 50000, "hyperlink": 50005}
    _MAX_ELEMENTS = 300
    _MAX_NATIVE_CHILD_WINDOWS = 64
    _MAX_NAME_CHARS = 300
    _MAX_EDIT_VALUE_CHARS = 500
    _EDIT_CONTROL_TYPES = {50004, 50030, 50031}
    _CONTROL_LABELS = {50000: "button", 50001: "calendar", 50002: "checkbox",
        50003: "combo_box", 50004: "edit", 50005: "hyperlink", 50006: "image",
        50007: "list_item", 50008: "list", 50009: "menu", 50010: "menu_bar",
        50011: "menu_item", 50012: "progress_bar", 50013: "radio_button",
        50014: "scroll_bar", 50015: "slider", 50016: "spinner", 50017: "status_bar",
        50018: "tab", 50019: "tab_item", 50020: "text", 50021: "tool_bar",
        50022: "tool_tip", 50023: "tree", 50024: "tree_item", 50025: "custom",
        50026: "group", 50027: "thumb", 50028: "data_grid", 50029: "data_item",
        50030: "document", 50031: "split_button", 50032: "window", 50033: "pane",
        50034: "header", 50035: "header_item", 50036: "table", 50037: "title_bar",
        50038: "separator", 50039: "semantic_zoom", 50040: "app_bar"}

    def __init__(self, controller=None):
        self.controller = controller

    @staticmethod
    def _connect():
        if os.name != "nt":
            raise RuntimeError("Windows UI Automation is available only on Windows")
        import ctypes
        import comtypes
        import comtypes.client

        comtypes.CoInitialize()
        try:
            module = comtypes.client.GetModule("UIAutomationCore.dll")
            automation = comtypes.client.CreateObject(module.CUIAutomation)
            hwnd = int(ctypes.windll.user32.GetForegroundWindow())
            if not hwnd:
                raise RuntimeError("No foreground window")
            window = automation.ElementFromHandle(hwnd)
            roots = [window]
            child_hwnds = WindowsUIAutomation._native_child_hwnds(hwnd)
            for child_hwnd in child_hwnds:
                try:
                    roots.append(automation.ElementFromHandle(child_hwnd))
                except Exception:
                    continue
            window = WindowsUIAutomation._best_accessible_root(module, automation, roots)
            return comtypes, module, automation, window
        except Exception:
            comtypes.CoUninitialize()
            raise

    @staticmethod
    def _native_child_hwnds(hwnd):
        """Return bounded descendant HWNDs belonging to the foreground window."""
        import ctypes
        from ctypes import wintypes

        rows = []
        truncated = False

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def visit(child, _):
            nonlocal truncated
            rows.append(int(child))
            if len(rows) >= WindowsUIAutomation._MAX_NATIVE_CHILD_WINDOWS:
                truncated = True
                return False
            return True

        if not ctypes.windll.user32.EnumChildWindows(hwnd, visit, 0):
            # EnumChildWindows returns zero both when there are no children and
            # when enumeration stops. Distinguish the intentional cap below.
            if truncated:
                raise RuntimeError("uia_native_child_window_tree_truncated")
        if truncated:
            raise RuntimeError("uia_native_child_window_tree_truncated")
        return rows

    @staticmethod
    def _best_accessible_root(module, automation, roots):
        """Prefer the foreground HWND subtree exposing the most real actions.

        Chromium/WebView2 can expose its title bar from the top-level HWND and
        the actual app controls only from a hosted child HWND. Restrict candidates
        to the foreground window and its native descendants, then retain one
        highest-scoring root so duplicated hosted fragments do not create false
        ambiguous targets.
        """
        best = None
        best_score = (-1, -1)
        for root in roots:
            try:
                items = WindowsUIAutomation._collect(module, automation, root)
                actions = sum(
                    1 for item in items
                    if item["enabled"] and not item["offscreen"] and item["name"]
                    and item["control_type"] in WindowsUIAutomation._CONTROL_TYPES.values()
                )
                score = (actions, len(items))
            except Exception:
                continue
            if score > best_score:
                best, best_score = root, score
        if best is None:
            raise RuntimeError("uia_accessible_root_unavailable")
        return best

    @staticmethod
    def _close(comtypes):
        try:
            comtypes.CoUninitialize()
        except Exception:
            pass

    @staticmethod
    def _typed_pattern(module, pattern, interface_name, member_name):
        """Get the requested interface from UIA's generic IUnknown pattern pointer."""
        member = getattr(pattern, member_name, None)
        if member is not None:
            return pattern
        interface = getattr(module, interface_name, None)
        query_interface = getattr(pattern, "QueryInterface", None)
        if interface is None or not callable(query_interface):
            raise RuntimeError("uia_pattern_interface_unavailable")
        typed = query_interface(interface)
        member = getattr(typed, member_name, None)
        if member is None:
            raise RuntimeError("uia_pattern_member_unavailable")
        return typed

    @staticmethod
    def _collect(module, automation, window):
        array = window.FindAll(module.TreeScope_Subtree, automation.CreateTrueCondition())
        elements = []
        for index in range(min(int(array.Length), WindowsUIAutomation._MAX_ELEMENTS)):
            element = array.GetElement(index)
            try:
                if bool(element.CurrentIsPassword) or bool(element.CurrentIsOffscreen):
                    continue
                name = str(element.CurrentName or "").strip()
                control_type = int(element.CurrentControlType)
                focused = bool(getattr(element, "CurrentHasKeyboardFocus", False))
                # Preserve an unnamed focused edit for safe focus/value verification,
                # while keeping unnamed controls out of general action discovery.
                if not name and not (focused and control_type in WindowsUIAutomation._EDIT_CONTROL_TYPES):
                    continue
                elements.append({
                    "name": name[:WindowsUIAutomation._MAX_NAME_CHARS],
                    "control_type": control_type,
                    "enabled": bool(element.CurrentIsEnabled),
                    "offscreen": bool(element.CurrentIsOffscreen),
                    "focused": focused,
                    "element": element,
                })
            except Exception:
                continue
        return elements

    def visible_texts(self):
        """Return foreground-window visible names internally for exact transition checks."""
        comtypes, module, automation, window = self._connect()
        try:
            return [item["name"] for item in self._collect(module, automation, window)]
        finally:
            self._close(comtypes)

    def focused_control(self):
        """Return safe metadata for the focused control, never its editable value."""
        comtypes, module, automation, window = self._connect()
        try:
            focused = [item for item in self._collect(module, automation, window)
                       if item.get("focused") and not item["offscreen"]]
            if len(focused) != 1:
                return {"ok": False, "error": "focused_control_not_unique"}
            item = focused[0]
            control_type = item["control_type"]
            editable = control_type in self._EDIT_CONTROL_TYPES
            safe_name = "" if editable else item["name"]
            # RuntimeId identifies the UIA element without hashing its potentially
            # sensitive value/name. Names and control types alone are not unique:
            # adjacent text boxes often share the same type and no safe name.
            runtime_id = item["element"].GetRuntimeId()
            if runtime_id is None:
                return {"ok": False, "error": "focused_control_runtime_id_unavailable"}
            runtime_parts = tuple(int(part) for part in runtime_id)
            if not runtime_parts:
                return {"ok": False, "error": "focused_control_runtime_id_unavailable"}
            identity = f"{control_type}:" + ",".join(map(str, runtime_parts))
            digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
            return {"ok": True, "control_type": control_type,
                    "role": self._CONTROL_LABELS.get(control_type, "unknown"),
                    "editable": editable, "name": safe_name,
                    "focus_sha256": digest}
        finally:
            self._close(comtypes)

    def focused_edit_value_fingerprint(self):
        """Return hash/length for one focused, non-password editable UIA value only."""
        comtypes, module, automation, window = self._connect()
        try:
            focused = [item for item in self._collect(module, automation, window)
                       if item.get("focused") and not item["offscreen"]]
            if len(focused) != 1:
                return {"ok": False, "error": "focused_control_not_unique"}
            item = focused[0]
            if item["control_type"] not in self._EDIT_CONTROL_TYPES:
                return {"ok": False, "error": "focused_control_not_editable"}
            element = item["element"]
            if bool(getattr(element, "CurrentIsPassword", False)):
                return {"ok": False, "error": "password_control_forbidden"}
            runtime_id = element.GetRuntimeId()
            if runtime_id is None:
                return {"ok": False, "error": "focused_control_runtime_id_unavailable"}
            runtime_parts = tuple(int(part) for part in runtime_id)
            if not runtime_parts:
                return {"ok": False, "error": "focused_control_runtime_id_unavailable"}
            identity = f'{item["control_type"]}:' + ",".join(map(str, runtime_parts))
            focus_digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
            try:
                pattern = element.GetCurrentPattern(module.UIA_ValuePatternId)
                pattern = self._typed_pattern(
                    module, pattern, "IUIAutomationValuePattern", "CurrentValue"
                )
                value = str(pattern.CurrentValue or "")
            except Exception:
                # Some native document controls (including current Notepad) expose
                # UIA TextPattern but not ValuePattern. Read only a bounded prefix;
                # exact typing accepts at most this same limit and fails closed if
                # the focused document is longer.
                pattern = element.GetCurrentPattern(module.UIA_TextPatternId)
                text_interface = getattr(module, "IUIAutomationTextPattern", None)
                query_interface = getattr(pattern, "QueryInterface", None)
                if text_interface is not None and callable(query_interface):
                    pattern = query_interface(text_interface)
                value = str(pattern.DocumentRange.GetText(self._MAX_EDIT_VALUE_CHARS + 1) or "")
            if len(value) > self._MAX_EDIT_VALUE_CHARS:
                return {"ok": False, "error": "focused_edit_value_too_long"}
            return {"ok": True, "focus_sha256": focus_digest,
                    "value_sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
                    "value_length": len(value)}
        except Exception as exc:
            return {"ok": False, "error": f"focused_edit_value_unavailable:{type(exc).__name__}"}
        finally:
            self._close(comtypes)

    def visible_element_bounds(self, name: str, role: str):
        """Return bounded geometry and opaque identities for exact visible UIA matches.

        This is intended for actions whose postcondition depends on the location of
        one accessible element. It never returns values from editable controls and
        keeps element names inside the action/verifier boundary.
        """
        requested = str(name or "").strip()
        requested_role = str(role or "").strip().casefold()
        if not requested or len(requested) > self._MAX_NAME_CHARS:
            raise ValueError("invalid_accessible_element_name")
        if requested_role not in set(self._CONTROL_LABELS.values()):
            raise ValueError("invalid_accessible_element_role")
        comtypes, module, automation, window = self._connect()
        try:
            elements = self._collect(module, automation, window)
            # _collect() caps work at _MAX_ELEMENTS. If the foreground tree hit
            # that cap, uniqueness cannot be established from a truncated view.
            if len(elements) >= self._MAX_ELEMENTS:
                return []
            result = []
            for item in elements:
                if (item["name"].casefold() != requested.casefold()
                        or self._CONTROL_LABELS.get(item["control_type"], "unknown") != requested_role):
                    continue
                try:
                    rect = item["element"].CurrentBoundingRectangle
                    bounds = [int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)]
                    runtime_id = item["element"].GetRuntimeId()
                    runtime_parts = tuple(int(part) for part in runtime_id) if runtime_id is not None else ()
                    if not runtime_parts:
                        continue
                    identity = f'{item["control_type"]}:' + ",".join(map(str, runtime_parts))
                    result.append({
                        "name": item["name"],
                        "role": requested_role,
                        "enabled": item["enabled"],
                        "bounds": bounds,
                        "identity_sha256": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
                    })
                except Exception:
                    continue
            return result[:20]
        finally:
            self._close(comtypes)

    def visible_actions(self):
        """List enabled, visible buttons/links in the current foreground window.

        This deliberately omits edit fields and other text-bearing controls so the
        observation can ground actions without dumping arbitrary form contents.
        Names are bounded by _collect and the result is capped independently.
        """
        comtypes, module, automation, window = self._connect()
        try:
            elements = self._collect(module, automation, window)
            actions = []
            for item in elements:
                if (item["enabled"] and item["control_type"] in self._CONTROL_TYPES.values()
                        and item["name"] and not item["offscreen"]):
                    role = next((name for name, value in self._CONTROL_TYPES.items()
                                 if value == item["control_type"]), "control")
                    actions.append({"name": item["name"], "role": role})
            return {"ok": True, "actions": actions[:100], "count": min(len(actions), 100)}
        finally:
            self._close(comtypes)

    def click_exact(self, name: str, expected_text: str, control_type: str = "Button"):
        requested = str(name or "").strip()
        expected = str(expected_text or "").strip()
        role = str(control_type or "Button").strip().casefold()
        control_value = self._CONTROL_TYPES.get(role)
        if (not requested or len(requested) > 180 or not expected or len(expected) > 256
                or control_value is None):
            return {"ok": False, "error": "invalid_accessibility_click_request"}
        controller = self.controller
        if (controller is None or not callable(getattr(controller, "screen_size", None))
                or not callable(getattr(controller, "is_foreground_window", None))
                or not callable(getattr(controller, "click", None))):
            return {"ok": False, "error": "desktop_click_controller_unavailable"}
        comtypes = None
        try:
            comtypes, module, automation, window = self._connect()
            elements = self._collect(module, automation, window)
            if len(elements) >= self._MAX_ELEMENTS:
                return {"ok": False, "error": "accessibility_tree_truncated"}
            if any(expected.casefold() in item["name"].casefold() for item in elements):
                return {"ok": False, "error": "expected_text_already_visible"}
            matches = [item for item in elements if item["enabled"] and not item["offscreen"]
                       and item["control_type"] == control_value
                       and item["name"].casefold() == requested.casefold()]
            if len(matches) != 1:
                return {"ok": False, "error": "accessibility_target_not_unique"}
            target = matches[0]["element"]
            hwnd = int(window.CurrentNativeWindowHandle)
            runtime_id = target.GetRuntimeId()
            runtime_id = tuple(int(part) for part in runtime_id) if runtime_id is not None else ()
            if hwnd <= 0 or not runtime_id:
                return {"ok": False, "error": "accessibility_target_identity_unavailable"}

            def bounds(element):
                rect = element.CurrentBoundingRectangle
                return tuple(int(getattr(rect, key)) for key in ("left", "top", "right", "bottom"))

            target_bounds = bounds(target)
            left, top, right, bottom = target_bounds
            size = controller.screen_size()
            width, height = int(size["width"]), int(size["height"])
            if (width <= 0 or height <= 0 or right <= left or bottom <= top
                    or left < 0 or top < 0 or right > width or bottom > height):
                return {"ok": False, "error": "accessibility_target_bounds_invalid"}
            x = left + (right - left - 1) // 2
            y = top + (bottom - top - 1) // 2
            if not controller.is_foreground_window(hwnd):
                return {"ok": False, "error": "foreground_window_changed"}

            # Reobserve immediately before the screen click. A changed UI tree,
            # target identity, rectangle or foreground window fails closed.
            fresh = self._collect(module, automation, window)
            if len(fresh) >= self._MAX_ELEMENTS:
                return {"ok": False, "error": "accessibility_tree_truncated"}
            if any(expected.casefold() in item["name"].casefold() for item in fresh):
                return {"ok": False, "error": "expected_text_already_visible"}
            fresh_matches = [item for item in fresh if item["enabled"] and not item["offscreen"]
                             and item["control_type"] == control_value
                             and item["name"].casefold() == requested.casefold()]
            if len(fresh_matches) != 1:
                return {"ok": False, "error": "accessibility_target_stale"}
            fresh_target = fresh_matches[0]["element"]
            fresh_id = fresh_target.GetRuntimeId()
            fresh_id = tuple(int(part) for part in fresh_id) if fresh_id is not None else ()
            if fresh_id != runtime_id or bounds(fresh_target) != target_bounds:
                return {"ok": False, "error": "accessibility_target_stale"}
            if not controller.is_foreground_window(hwnd):
                return {"ok": False, "error": "foreground_window_changed"}
            controller.click(x, y)
            return {
                "ok": True,
                "action": "desktop_click_accessible",
                "target_sha256": hashlib.sha256(requested.casefold().encode("utf-8")).hexdigest(),
                "_postcondition_context": {
                    "expected_absent_before": True,
                    "expected_text_sha256": hashlib.sha256(expected.casefold().encode("utf-8")).hexdigest(),
                },
            }
        except Exception as exc:
            return {"ok": False, "error": f"windows_uia_action_failed:{type(exc).__name__}"}
        finally:
            if comtypes is not None:
                self._close(comtypes)
