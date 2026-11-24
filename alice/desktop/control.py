"""Small Windows desktop helpers used by Alice's always-awake shell."""
from __future__ import annotations
import ctypes
import os
import threading
from ctypes import wintypes

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
WM_HOTKEY = 0x0312

class GlobalHotkey:
    """Register Ctrl+Alt+A on Windows and call a callback when pressed."""
    def __init__(self, callback, vk=ord("A"), hotkey_id=0xA11CE):
        self.callback=callback; self.vk=vk; self.hotkey_id=hotkey_id
        self._thread=None; self._stop=threading.Event(); self._registered=False
    @property
    def available(self): return os.name == "nt"
    def start(self):
        if not self.available or (self._thread and self._thread.is_alive()): return False
        self._stop.clear(); self._thread=threading.Thread(target=self._loop,daemon=True,name="alice-hotkey"); self._thread.start(); return True
    def _loop(self):
        user32=ctypes.windll.user32
        if not user32.RegisterHotKey(None,self.hotkey_id,MOD_CONTROL|MOD_ALT,self.vk): return
        self._registered=True
        try:
            msg=wintypes.MSG()
            while not self._stop.is_set() and user32.GetMessageW(ctypes.byref(msg),None,0,0)>0:
                if msg.message==WM_HOTKEY and msg.wParam==self.hotkey_id:
                    try:self.callback()
                    except Exception:pass
        finally:
            user32.UnregisterHotKey(None,self.hotkey_id); self._registered=False
    def stop(self):
        self._stop.set()
        # The thread owns the Windows message queue; WM_QUIT is posted by id when possible.
        if self._thread and self._thread.is_alive():
            try: ctypes.windll.user32.PostThreadMessageW(self._thread.ident, 0x0012, 0, 0)
            except Exception: pass
