
import ctypes
import time

def _gui():
    import pyautogui
    return pyautogui

class ComputerController:
    def __init__(self):
        gui = _gui()
        gui.PAUSE=0.15
        gui.FAILSAFE=True

    def screen_size(self):
        w,h=_gui().size()
        return {"width":w,"height":h}

    def is_foreground_window(self,hwnd):
        """Return whether hwnd belongs to the current foreground window.

        UI Automation may anchor on a WebView child HWND. Accept that child only
        when its GA_ROOT ancestor is the exact current foreground HWND.
        """
        try:
            target=int(hwnd)
            if target<=0:
                return False
            user32=ctypes.windll.user32
            foreground=int(user32.GetForegroundWindow())
            root=int(user32.GetAncestor(target,2))
            return foreground>0 and (foreground==target or root==foreground)
        except Exception:
            return False

    def mouse_position(self):
        x,y=_gui().position()
        return {"x":x,"y":y}

    def move(self,x,y,duration=0.2):
        _gui().moveTo(int(x),int(y),duration=float(duration))
        return self.mouse_position()

    def click(self,x=None,y=None,button="left",clicks=1):
        if x is not None and y is not None:
            _gui().moveTo(int(x),int(y),duration=.15)
        _gui().click(button=button,clicks=int(clicks))
        return "clicked"

    def double_click(self,x=None,y=None):
        return self.click(x,y,clicks=2)

    def scroll(self,amount):
        _gui().scroll(int(amount))
        return "scrolled"

    def type_text(self,text,interval=0.01):
        _gui().write(str(text),interval=float(interval))
        return "typed"

    def hotkey(self,*keys):
        _gui().hotkey(*keys)
        return "hotkey executed"

    def press(self,key):
        _gui().press(key)
        return "key pressed"

    def drag(self,x1,y1,x2,y2,duration=.5):
        _gui().moveTo(int(x1),int(y1),duration=.1)
        _gui().dragTo(int(x2),int(y2),duration=float(duration))
        return "dragged"
