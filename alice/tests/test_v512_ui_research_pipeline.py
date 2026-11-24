from pathlib import Path
from types import SimpleNamespace
from threading import Event
from alice.cognitive.core import CognitiveCore
from alice.memory.store import MemoryStore
from alice.brain.intent_router import IntentRouter
from alice.knowledge.acquirer import KnowledgeAcquirer

from alice.ui.app import AliceUI


def test_research_extractive_fallback_returns_a_cited_source_sentence():
    source_text = (
        "Path.resolve() makes the path absolute, resolving any symbolic links. "
        "The exact behavior is described in the official pathlib documentation."
    )
    answer, claims = KnowledgeAcquirer._extractive_fallback(
        "Python pathlib Path.resolve documentation",
        [{"ref": 1, "source": "https://docs.python.org/3/library/pathlib.html",
          "text": source_text}],
    )

    assert "Path.resolve()" in answer
    assert answer.endswith("[1].")
    assert KnowledgeAcquirer._check_citations(answer, {1})["ok"] is True
    assert KnowledgeAcquirer._check_numeric_support(
        claims, {1: {"text": source_text}})["ok"] is True


def test_research_fallback_prefers_official_docs_over_noisy_snippets():
    answer, claims = KnowledgeAcquirer._extractive_fallback(
        "Python pathlib Path.resolve documentation",
        [
            {"ref": 1, "source": "https://example.com/blog",
             "text": "Path.resolve() in Python pathlib makes paths absolute and resolves links. "
                     "Python pathlib Path.resolve documentation explains how Path.resolve works."},
            {"ref": 2, "source": "https://docs.python.org/3/library/pathlib.html",
             "text": "Path.resolve(strict=False) makes the path absolute, resolving any symlinks."},
        ],
    )

    assert answer.endswith("[2].")
    assert claims[0]["source_refs"] == [2]


def test_research_fallback_skips_official_code_examples_for_explanatory_prose():
    answer, claims = KnowledgeAcquirer._extractive_fallback(
        "Python pathlib Path.resolve documentation",
        [{"ref": 1, "source": "https://docs.python.org/3/library/pathlib.html",
          "text": "resolve() PosixPath('/etc/rc.d/init.d/halt') Querying path properties. "
                  "Path.resolve() makes the path absolute and resolves symbolic links."}],
    )

    assert "makes the path absolute" in answer
    assert "PosixPath" not in answer
    assert claims[0]["source_refs"] == [1]


def test_premium_event_polling_prevents_overlapping_replays():
    html = Path(__file__).parents[1] / "ui" / "assets" / "alice-premium-ui.html"
    text = html.read_text(encoding="utf-8")

    assert "let eventCursor=0,streamBubble=null,pollInFlight=false;" in text
    assert "async function pollRuntime(){if(pollInFlight)return;" in text
    assert "finally{pollInFlight=false}" in text


def test_app_research_uses_acquirer_and_requires_readback_for_verified_answer():
    class Acquirer:
        def __init__(self):
            self.query = None

        def acquire(self, query, max_sources):
            self.query = (query, max_sources)
            return {"ok": True, "status": "acquired",
                    "conclusion": "A sourced answer [1].\n\nSources:\n[1] https://example.com/a"}

        def verify_acquisition_postcondition(self, args, result):
            return SimpleNamespace(ok=True)

    app = AliceUI.__new__(AliceUI)
    app.knowledge_acquirer = Acquirer()

    result = app._perform_web_research("research this", "topic")

    assert app.knowledge_acquirer.query == ("topic", 5)
    assert result["research_status"] == "acquired"
    assert result["research_verified"] is True
    assert "A sourced answer [1]." in result["result"]


def test_app_withholds_summary_when_saved_research_readback_fails():
    class Acquirer:
        def acquire(self, _query, max_sources):
            return {"ok": True, "status": "acquired",
                    "conclusion": "Unsupported summary [1].\n\nSources:\n[1] https://example.com/a"}

        def verify_acquisition_postcondition(self, _args, _result):
            return SimpleNamespace(ok=False)

    app = AliceUI.__new__(AliceUI)
    app.knowledge_acquirer = Acquirer()

    result = app._perform_web_research("research this", "topic")

    assert result["research_verified"] is False
    assert "withholding the summary" in result["result"]
    assert "Unsupported summary" not in result["result"]
    assert "https://example.com/a" in result["result"]


def test_app_reports_no_source_synthesis_honestly():
    class Acquirer:
        def acquire(self, _query, max_sources):
            return {"ok": False, "status": "no_sources",
                    "conclusion": "No usable public sources were retrieved."}

        def verify_acquisition_postcondition(self, *_args):
            raise AssertionError("failed acquisition must not pass readback")

    app = AliceUI.__new__(AliceUI)
    app.knowledge_acquirer = Acquirer()

    result = app._perform_web_research("research this", "topic")

    assert result["research_status"] == "no_sources"
    assert result["research_verified"] is False
    assert result["result"] == "No usable public sources were retrieved."


def test_worker_routes_research_requests_through_verified_acquirer():
    class Acquirer:
        def __init__(self):
            self.calls = []

        def acquire(self, query, max_sources):
            self.calls.append((query, max_sources))
            return {"ok": True, "status": "acquired",
                    "conclusion": "PurePath.name returns its final component [1].\n\n"
                                  "Sources:\n[1] https://docs.python.org/3/library/pathlib.html"}

        def verify_acquisition_postcondition(self, _args, _result):
            return SimpleNamespace(ok=True)

    app = AliceUI.__new__(AliceUI)
    app.conversation = SimpleNamespace(append=lambda *_args: None)
    app.memory = SimpleNamespace(learn_from_chat=lambda *_args: None,
                                  learn_explicit=lambda *_args: None)
    app.cognitive = SimpleNamespace(decide=lambda *_args: SimpleNamespace(
        handled=False, response=None))
    app.intent_router = SimpleNamespace(
        requested_url=lambda _text: None,
        requested_app=lambda _text: None,
        web_query=lambda _text: "pathlib PurePath.name official documentation")
    app.knowledge_acquirer = Acquirer()
    persisted = []
    queued = []
    app._is_hypothetical_analysis = lambda _text: False
    app._direct_local_command = lambda _text: None
    app._persist_assistant_result = lambda text, result: persisted.append((text, result))
    app._queue_ui = lambda *args: queued.append(args)

    app.worker("Research the official Python docs for PurePath.name", Event())

    assert app.knowledge_acquirer.calls == [
        ("pathlib PurePath.name official documentation", 5)]
    assert len(persisted) == 1
    assert persisted[0][1]["research_verified"] is True
    assert "https://docs.python.org/3/library/pathlib.html" in persisted[0][1]["result"]
    assert queued[-1][0] == "finish"
    assert queued[-1][1]["research_verified"] is True


def test_explicit_research_with_no_file_changes_constraint_skips_hypothetical_chat():
    class Acquirer:
        def __init__(self):
            self.calls = []

        def acquire(self, query, max_sources):
            self.calls.append((query, max_sources))
            return {"ok": True, "status": "acquired",
                    "conclusion": "Path.resolve returns an absolute path [1].\n\n"
                                  "Sources:\n[1] https://docs.python.org/3/library/pathlib.html"}

        def verify_acquisition_postcondition(self, _args, _result):
            return SimpleNamespace(ok=True)

    prompt = ("Research the official Python pathlib documentation. Briefly explain "
              "what Path.resolve() does. Do not modify files.")
    app = AliceUI.__new__(AliceUI)
    app.conversation = SimpleNamespace(append=lambda *_args: None)
    app.memory = SimpleNamespace(learn_from_chat=lambda *_args: None,
                                  learn_explicit=lambda *_args: None)
    app.cognitive = SimpleNamespace(decide=lambda *_args: SimpleNamespace(
        handled=False, response=None))
    app.intent_router = SimpleNamespace(
        is_explicit_web_search=IntentRouter.is_explicit_web_search,
        requested_url=lambda _text: None,
        requested_app=lambda _text: None,
        web_query=IntentRouter.web_query)
    app.knowledge_acquirer = Acquirer()
    persisted = []
    queued = []
    app._direct_local_command = lambda _text: None
    app._persist_assistant_result = lambda text, result: persisted.append((text, result))
    app._queue_ui = lambda *args: queued.append(args)

    assert app._is_hypothetical_analysis(prompt) is True
    app.worker(prompt, Event())

    assert len(app.knowledge_acquirer.calls) == 1
    assert app.knowledge_acquirer.calls[0][1] == 5
    assert persisted[0][1]["research_verified"] is True
    assert queued[-1][0] == "finish"


def test_worker_returns_structured_persistent_memory_without_model_call(tmp_path):
    memory = MemoryStore(root=tmp_path)
    saved = memory.manager.set(
        "response style", "Use concise replies", kind="preference", source="user")
    app = AliceUI.__new__(AliceUI)
    app.conversation = SimpleNamespace(append=lambda *_args: None)
    app.memory = memory
    app.cognitive = CognitiveCore(memory=memory, root=tmp_path)
    persisted = []
    queued = []
    app._is_hypothetical_analysis = lambda _text: False
    app._persist_assistant_result = lambda text, result: persisted.append((text, result))
    app._queue_ui = lambda *args: queued.append(args)

    app.worker("What do you remember?", Event())

    assert len(persisted) == 1
    assert f"ID: {saved.id[:8]}" in persisted[0][1]["result"]
    assert "Use concise replies" in persisted[0][1]["result"]
    assert queued[-1][0] == "finish"
    assert "Use concise replies" in queued[-1][1]["result"]


def test_worker_correction_by_memory_id_survives_store_recreation(tmp_path):
    memory = MemoryStore(root=tmp_path)
    saved = memory.manager.set(
        "response style", "Use concise replies", kind="preference", source="user")
    app = AliceUI.__new__(AliceUI)
    app.conversation = SimpleNamespace(append=lambda *_args: None)
    app.memory = memory
    app.cognitive = CognitiveCore(memory=memory, root=tmp_path)
    persisted = []
    app._is_hypothetical_analysis = lambda _text: False
    app._persist_assistant_result = lambda text, result: persisted.append((text, result))
    app._queue_ui = lambda *_args: None

    app.worker(
        f"correct memory {saved.id[:8]} => Use brief answers with the key detail",
        Event())

    assert persisted[0][1]["result"] == "Memory corrected."
    restarted = MemoryStore(root=tmp_path)
    records = restarted.manager.list("response style")
    assert len(records) == 1
    assert records[0].value == "Use brief answers with the key detail"
    assert records[0].supersedes == saved.id


def test_worker_forgetting_by_memory_id_persists_without_touching_other_records(tmp_path):
    memory = MemoryStore(root=tmp_path)
    target = memory.manager.set(
        "response style", "Use concise replies", kind="preference", source="user")
    other = memory.manager.set(
        "project name", "ALICE", kind="project_context", source="user")
    app = AliceUI.__new__(AliceUI)
    app.conversation = SimpleNamespace(append=lambda *_args: None)
    app.memory = memory
    app.cognitive = CognitiveCore(memory=memory, root=tmp_path)
    persisted = []
    app._is_hypothetical_analysis = lambda _text: False
    app._persist_assistant_result = lambda text, result: persisted.append((text, result))
    app._queue_ui = lambda *_args: None

    app.worker(f"forget memory {target.id[:8]}", Event())

    assert "Forgot 1" in persisted[0][1]["result"]
    restarted = MemoryStore(root=tmp_path)
    active = restarted.manager.list()
    assert [record.id for record in active] == [other.id]
