"""Optional, readable HUD-themed chat window for Alice."""
from __future__ import annotations

import tkinter as tk
from tkinter import scrolledtext


class HUDChatbox:
    COLORS = {
        "background": "#07131f",
        "panel": "#0b1d2b",
        "panel_alt": "#102638",
        "border": "#1aa8c8",
        "cyan": "#61e6ff",
        "text": "#d9f4ff",
        "muted": "#7ea6b8",
        "magenta": "#e77db8",
        "button": "#12364a",
    }

    def __init__(self, master, on_submit, on_close, version=""):
        self.on_submit = on_submit
        self.on_close = on_close
        self._closed = False
        self._streaming = False
        c = self.COLORS

        self.window = tk.Toplevel(master)
        self.window.title("ALICE · HUD CHAT")
        self.window.geometry("480x680")
        self.window.minsize(380, 480)
        self.window.configure(bg=c["background"])
        self.window.transient(master)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.close())

        shell = tk.Frame(self.window, bg=c["background"], highlightthickness=1,
                         highlightbackground=c["border"])
        shell.pack(fill="both", expand=True, padx=9, pady=9)

        header = tk.Frame(shell, bg=c["panel"], padx=14, pady=10)
        header.pack(fill="x", padx=1, pady=(1, 6))
        tk.Label(header, text="ALICE", bg=c["panel"], fg=c["cyan"],
                 font=("Segoe UI", 17, "bold")).pack(side="left")
        tk.Label(header, text="  /  HUD CHAT", bg=c["panel"], fg=c["muted"],
                 font=("Segoe UI", 9, "bold")).pack(side="left", pady=(7, 0))
        tk.Label(header, text=f"● READY   {version}", bg=c["panel"], fg=c["cyan"],
                 font=("Segoe UI", 8)).pack(side="right", pady=(7, 0))

        instrument = tk.Canvas(shell, height=74, bg=c["panel"], highlightthickness=0)
        instrument.pack(fill="x", padx=1, pady=(0, 6))
        instrument.create_oval(190, 7, 270, 67, outline=c["border"], width=2)
        instrument.create_oval(202, 18, 258, 56, outline=c["cyan"], width=1)
        instrument.create_arc(196, 11, 264, 63, start=205, extent=105,
                             style="arc", outline=c["magenta"], width=2)
        instrument.create_line(18, 37, 174, 37, fill=c["border"], width=1)
        instrument.create_line(286, 37, 442, 37, fill=c["border"], width=1)
        instrument.create_text(18, 19, anchor="w", text="CONVERSATION LINK",
                               fill=c["muted"], font=("Consolas", 8))
        instrument.create_text(462, 56, anchor="e", text="LOCAL UI",
                               fill=c["muted"], font=("Consolas", 8))

        self.transcript = scrolledtext.ScrolledText(
            shell, wrap=tk.WORD, state="disabled", font=("Segoe UI", 10),
            bg=c["panel_alt"], fg=c["text"], insertbackground=c["cyan"],
            selectbackground="#1b6077", relief="flat", padx=12, pady=10,
        )
        self.transcript.pack(fill="both", expand=True, padx=1, pady=(0, 7))
        self.transcript.tag_configure("speaker_you", foreground=c["cyan"],
                                      font=("Segoe UI", 9, "bold"))
        self.transcript.tag_configure("speaker_alice", foreground=c["magenta"],
                                      font=("Segoe UI", 9, "bold"))
        self.transcript.tag_configure("speaker_other", foreground=c["muted"],
                                      font=("Segoe UI", 9, "bold"))

        footer = tk.Frame(shell, bg=c["panel"], padx=8, pady=8)
        footer.pack(fill="x", padx=1, pady=(0, 1))
        self.input = tk.Entry(footer, font=("Segoe UI", 11), bg="#06111b",
                              fg=c["text"], insertbackground=c["cyan"],
                              relief="flat", highlightthickness=1,
                              highlightbackground=c["border"])
        self.input.pack(side="left", fill="x", expand=True, ipady=8, padx=(0, 7))
        self.input.bind("<Return>", self._submit_event)
        tk.Button(footer, text="SEND", command=self.submit, bg=c["button"],
                  fg=c["cyan"], activebackground=c["border"], activeforeground="#04111b",
                  relief="flat", padx=14, pady=7, font=("Segoe UI", 9, "bold")).pack(side="right")
        self.input.focus_set()

    def _insert(self, text, tag=None):
        self.transcript.configure(state="normal")
        if tag:
            self.transcript.insert("end", text, tag)
        else:
            self.transcript.insert("end", text)
        self.transcript.see("end")
        self.transcript.configure(state="disabled")

    def append(self, speaker, text):
        if self._closed or text is None or text == "":
            return
        key = str(speaker).strip().casefold()
        tag = "speaker_you" if key == "you" else "speaker_alice" if key == "alice" else "speaker_other"
        self._insert(f"{speaker}: ", tag)
        self._insert(f"{text}\n\n")

    def begin_stream(self):
        if self._closed or self._streaming:
            return
        self._streaming = True
        self._insert("Alice: ", "speaker_alice")

    def stream(self, piece):
        if self._streaming and not self._closed:
            self._insert(str(piece))

    def end_stream(self):
        if self._streaming and not self._closed:
            self._insert("\n\n")
            self._streaming = False

    def clear(self):
        if self._closed:
            return
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        self.transcript.configure(state="disabled")

    def focus_input(self):
        if not self._closed:
            self.input.focus_set()

    def submit(self):
        if self._closed:
            return False
        text = self.input.get().strip()
        if not text:
            return False
        self.input.delete(0, "end")
        self.on_submit(text)
        return True

    def _submit_event(self, _event):
        self.submit()
        return "break"

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.window.destroy()
        finally:
            self.on_close()
