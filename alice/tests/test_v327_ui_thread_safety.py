from pathlib import Path


def test_ui_queue_is_present_and_worker_never_calls_tk_directly():
    text=(Path(__file__).resolve().parents[1]/"ui"/"app.py").read_text(encoding="utf-8")
    assert "import os, threading, tkinter as tk, sys, subprocess, queue" in text
    assert "self._ui_queue=queue.Queue()" in text
    assert "self.root.after(25,self._drain_ui_queue)" in text
    start=text.index("    def worker(self,text,cancel_event):")
    end=text.index("    def finish(self,result,cancel_event):", start)
    worker=text[start:end]
    assert "self.root.after" not in worker
    assert 'self._queue_ui("stream_append"' in worker


def test_knowledge_acquirer_created_before_tools():
    text=(Path(__file__).resolve().parents[1]/"ui"/"app.py").read_text(encoding="utf-8")
    # These initializers currently share a compact line; compare the source
    # offsets globally so harmless formatting changes do not break the check.
    assert text.index("self.knowledge_acquirer=KnowledgeAcquirer") < text.index("self.tools=self.build_tools()")
