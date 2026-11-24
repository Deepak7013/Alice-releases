from types import SimpleNamespace
import socket

import pytest


@pytest.fixture
def public_dns(monkeypatch):
    monkeypatch.setattr(
        "alice.research.web_research.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))],
    )


def test_openrouter_is_blocked_before_network_call_in_local_only_mode(monkeypatch):
    from alice.providers.router import ProviderError, Router

    monkeypatch.setenv("ALICE_PROVIDER_MAX_OUTPUT_TOKENS", "2048")
    monkeypatch.setenv("ALICE_RUNTIME_MODE", "local_required")
    router = Router(provider="openrouter")
    calls = []
    router._ask_openrouter = lambda *args, **kwargs: calls.append((args, kwargs))
    with pytest.raises(ProviderError) as error:
        router._call_one("openrouter", "short bounded grounding request", None, None)

    assert calls == []
    assert "disabled" in str(error.value).lower() or "local" in str(error.value).lower()


def test_google_js_retry_page_falls_back_to_duckduckgo_and_unwraps_source(monkeypatch):
    from alice.research.web_research import WebResearch

    pages = {
        "https://www.google.com/search": """
            <html><title>Google Search</title><body>
              <p>To use search, enable JavaScript.</p>
              <a href="/httpservice/retry/enablejs">here</a>
              <a href="/search">click here</a>
            </body></html>
        """,
        "https://html.duckduckgo.com/html/": """
            <html><title>Search</title><body>
              <div class="result">
                <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.python.org%2F3%2Flibrary%2Fpathlib.html&amp;rut=tracking">
                  pathlib documentation
                </a>
                <a class="result__snippet">PurePath.name returns the final component.</a>
              </div>
            </body></html>
        """,
    }
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(status_code=200, text=pages[url], raise_for_status=lambda: None)

    monkeypatch.setattr("alice.research.web_research.requests.get", get)
    result = WebResearch().search("Python pathlib PurePath name official documentation")

    assert calls == ["https://www.google.com/search", "https://html.duckduckgo.com/html/"]
    assert result["results"] == [{
        "title": "pathlib documentation",
        "url": "https://docs.python.org/3/library/pathlib.html",
        "snippet": "PurePath.name returns the final component.",
    }]


def test_fetch_text_extracts_publication_date_and_records_retrieval_time(monkeypatch, public_dns):
    from alice.research.web_research import WebResearch

    html = """
        <html><head><title>Current article</title>
        <meta property="article:published_time" content="2026-08-12T09:30:00Z">
        </head><body><article>Useful factual text.</article></body></html>
    """
    monkeypatch.setattr(
        "alice.research.web_research.requests.get",
        lambda *_args, **_kwargs: SimpleNamespace(
            text=html, raise_for_status=lambda: None
        ),
    )

    result=WebResearch().fetch_text("https://example.com/article")

    assert result["published_at"] == "2026-08-12T09:30:00Z"
    assert result["retrieved_at_epoch"] > 0
    assert "+00:00" in result["retrieved_at"]
    assert "Useful factual text." in result["text"]


def test_fetch_text_prefers_article_content_over_navigation(monkeypatch, public_dns):
    from alice.research.web_research import WebResearch

    html = """
        <html><head><title>Facts</title></head><body>
        <nav>Home Mission News Search navigation filler</nav>
        <main><h1>Moon count</h1><p>As of June 2026, Saturn has 293 confirmed moons.</p></main>
        <footer>Privacy Contact Terms footer filler</footer>
        </body></html>
    """
    monkeypatch.setattr(
        "alice.research.web_research.requests.get",
        lambda *_args, **_kwargs: SimpleNamespace(text=html, raise_for_status=lambda: None),
    )

    result=WebResearch().fetch_text("https://example.com/facts")

    assert "293 confirmed moons" in result["text"]
    assert "navigation filler" not in result["text"]
    assert "footer filler" not in result["text"]


def test_fetch_rejects_private_literal_hosts_and_nonstandard_ports():
    from alice.research.web_research import WebResearch

    for url in (
        "http://127.0.0.1/admin",
        "http://192.168.1.20/",
        "http://localhost/",
        "https://example.com:8443/",
        "https://user:secret@example.com/",
    ):
        with pytest.raises(ValueError):
            WebResearch()._validate_public_url(url)


def test_fetch_rejects_domains_resolving_to_private_addresses(monkeypatch):
    from alice.research.web_research import WebResearch

    monkeypatch.setattr(
        "alice.research.web_research.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443))],
    )
    with pytest.raises(ValueError, match="non-public"):
        WebResearch()._validate_public_url("https://example.com/")


def test_fetch_revalidates_redirect_destinations(monkeypatch, public_dns):
    from alice.research.web_research import WebResearch

    calls=[]
    def get(url, **_kwargs):
        calls.append(url)
        return SimpleNamespace(status_code=302,headers={"Location":"http://127.0.0.1/internal"},
                               raise_for_status=lambda:None,close=lambda:None)
    monkeypatch.setattr("alice.research.web_research.requests.get",get)
    with pytest.raises(ValueError,match="Private or non-public"):
        WebResearch().fetch_text("https://example.com/redirect")
    assert calls == ["https://example.com/redirect"]


def test_fetch_rejects_oversized_page_body(monkeypatch, public_dns):
    from alice.research.web_research import WebResearch

    class Response:
        status_code=200
        headers={"Content-Type":"text/html"}
        encoding="utf-8"
        def raise_for_status(self): pass
        def close(self): pass
        def iter_content(self,chunk_size):
            yield b"x" * WebResearch.MAX_PAGE_BYTES
            yield b"x"

    monkeypatch.setattr("alice.research.web_research.requests.get",lambda *_a,**_k:Response())
    with pytest.raises(ValueError,match="2 MiB"):
        WebResearch().fetch_text("https://example.com/large")


def test_fetch_decodes_utf8_html_using_declared_charset(monkeypatch, public_dns):
    from alice.research.web_research import WebResearch

    class Response:
        status_code=200
        headers={"Content-Type":"text/html; charset=iso-8859-1"}
        encoding="iso-8859-1"
        def raise_for_status(self): pass
        def close(self): pass
        def iter_content(self,chunk_size):
            yield '<html><head><meta charset="utf-8"><title>ALICE — research</title></head><body><main>café facts</main></body></html>'.encode("utf-8")

    monkeypatch.setattr("alice.research.web_research.requests.get",lambda *_a,**_k:Response())
    page=WebResearch().fetch_text("https://example.com/utf8")
    assert page["title"] == "ALICE — research"
    assert "café facts" in page["text"]


def test_knowledge_acquirer_passes_retrieved_source_into_synthesis(tmp_path):
    from alice.knowledge.acquirer import KnowledgeAcquirer

    source_url = "https://docs.python.org/3/library/pathlib.html"
    evidence_text = "PurePath.name returns the final path component, excluding the drive and root."

    class FakeRouter:
        def __init__(self):
            self.prompts = []

        def ask(self, prompt, **kwargs):
            self.prompts.append(prompt)
            return f"PurePath.name returns the final path component [1]."

    class FakeResearch:
        def search(self, query, max_results=4):
            return {"results": [{"url": source_url, "title": "pathlib documentation"}]}

        def fetch_text(self, url, max_chars=12000):
            return {"url": url, "title": "pathlib documentation", "text": evidence_text}

    router = FakeRouter()
    result = KnowledgeAcquirer(router, FakeResearch(), tmp_path).acquire("What does PurePath.name return?", max_sources=1)

    synthesis_prompt = router.prompts[0]
    assert source_url in synthesis_prompt
    assert evidence_text in synthesis_prompt
    assert result["ok"] is True
    assert source_url in result["conclusion"]
    assert "final path component" in result["conclusion"]
