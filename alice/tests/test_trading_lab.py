import copy
import csv
from datetime import date, timedelta

import pytest

from alice.finance.backtest import _simulate, backtest_daily, load_daily_csv
from alice.finance.service import TradingLab, is_trading_request, register_trading_tools
from alice.tools.registry import ToolRegistry


def bars(count=40, rising=True):
    rows = []
    for i in range(count):
        value = 100 + i if rising else 100 - i
        rows.append({"date": date(2020, 1, 1) + timedelta(days=i),
                     "open": value, "high": value + 1, "low": value - 1, "close": value})
    return rows


def csv_file(root, rows):
    target = root / "data" / "workspace" / "market" / "sample.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return target


def test_cost_accounting_on_flat_market():
    data = bars(3)
    for bar in data:
        bar.update(open=100, high=100, low=100, close=100)
    result = _simulate(data, [True] * 3, 0, 3, 1000, 10, 100, 1)
    assert result["final_equity"] == pytest.approx(980.2)
    assert result["fees_paid"] == pytest.approx(1.8)
    assert result["slippage_cost"] == pytest.approx(18)
    assert result["orders"][0]["shares"] == 9
    assert result["orders"][-1]["terminal_liquidation"] is True
    assert result["max_drawdown_pct"] == pytest.approx(1.98)


def test_current_close_cannot_change_current_open_order():
    original = bars(40, rising=False)
    changed = copy.deepcopy(original)
    changed[32].update(close=200, high=201)
    before = backtest_daily(original, fast=2, slow=4)["test_period"]["orders"]
    after = backtest_daily(changed, fast=2, slow=4)["test_period"]["orders"]
    cut = changed[32]["date"].isoformat()
    assert [o for o in before if o["date"] <= cut] == [o for o in after if o["date"] <= cut]
    assert after[0]["date"] == changed[33]["date"].isoformat()
    assert after[0]["reference_price"] == changed[33]["open"]


def test_holdout_starts_fresh_and_benchmark_uses_identical_dates():
    result = backtest_daily(bars(), fast=2, slow=4, capital=1000, fee_bps=0, slippage_bps=0)
    test = result["test_period"]
    benchmark = result["buy_and_hold_same_test_period"]
    assert result["training_period"]["end"] < test["start"]
    assert test["initial_capital"] == 1000
    assert test["orders"][0]["date"] == test["start"]
    assert (test["start"], test["end"]) == (benchmark["start"], benchmark["end"])
    assert result["test_excess_return_percentage_points"] == pytest.approx(0)


def test_no_trades_and_losses_are_reported_without_invented_win_rate():
    result = backtest_daily(bars(rising=False), fast=2, slow=4)
    assert result["test_period"]["win_rate_pct"] is None
    assert result["test_period"]["return_pct"] == 0
    assert result["buy_and_hold_same_test_period"]["return_pct"] < 0


@pytest.mark.parametrize("changes", [dict(close="nan"), dict(low=999), dict(open=0), dict(volume=-1)])
def test_malformed_prices_rejected(tmp_path, changes):
    rows = bars()
    if "volume" in changes:
        for row in rows:
            row["volume"] = 1
    rows[5].update(changes)
    with pytest.raises(ValueError):
        load_daily_csv(csv_file(tmp_path, rows))


def test_duplicate_dates_and_multiple_securities_rejected(tmp_path):
    rows = bars()
    rows[4]["date"] = rows[3]["date"]
    with pytest.raises(ValueError, match="strictly increasing"):
        load_daily_csv(csv_file(tmp_path, rows))
    rows = bars()
    for i, row in enumerate(rows):
        row["symbol"] = "A" if i < 20 else "B"
    with pytest.raises(ValueError, match="one security"):
        load_daily_csv(csv_file(tmp_path, rows))


@pytest.mark.parametrize("options", [dict(fast=4, slow=2), dict(slow=30), dict(allocation=2),
                                     dict(fee_bps=float("nan")), dict(slippage_bps=-1)])
def test_invalid_simulation_inputs_rejected(options):
    with pytest.raises(ValueError):
        backtest_daily(bars(20), **options)


def test_dataset_scope_and_provenance(tmp_path):
    lab = TradingLab(tmp_path)
    csv_file(tmp_path, bars())
    report = lab.backtest("market/sample.csv", fast=2, slow=4, currency="INR")
    assert report["simulation_only"] is True
    assert len(report["dataset"]["sha256"]) == 64
    assert report["dataset"]["adjustments_verified"] is False
    assert any("Unadjusted" in line for line in report["limitations"])
    outside = tmp_path / "outside.csv"
    outside.write_text("private", encoding="utf-8")
    with pytest.raises(ValueError, match="inside data/workspace"):
        lab.backtest(str(outside), fast=2, slow=4)


def test_primary_sources_are_filtered_and_never_marked_trusted(tmp_path, monkeypatch):
    class Search:
        def search(self, query, max_results):
            return {"results": [{"url": url} for url in [
                "https://nseindia.com.evil.example/news", "http://localhost/data",
                "https://www.nseindia.com/all-reports"]]}
    lab = TradingLab(tmp_path, Search())
    fetched = []
    def fetch(url):
        fetched.append(url)
        return {"title": "Official reports", "text": "Daily historical reports are available."}
    monkeypatch.setattr(lab, "_fetch", fetch)
    result = lab.research("historical stock data", market="india")
    assert fetched == ["https://www.nseindia.com/all-reports"]
    source = result["sources"][0]
    assert source["published_at"] is None and source["retrieved_at"]
    assert not lab.store.get(source["knowledge_id"]).trusted


def test_empty_internet_results_report_no_sources(tmp_path):
    class Search:
        def search(self, query, max_results):
            return {"results": []}
    assert TradingLab(tmp_path, Search()).research("stocks")["status"] == "no_sources"


def test_direct_official_source_works_without_search(tmp_path, monkeypatch):
    lab = TradingLab(tmp_path)
    monkeypatch.setattr(lab, "_fetch", lambda url: {"title": "Risk", "text": "Markets involve risk."})
    result = lab.research("risk", market="us", source_url="https://www.investor.gov/risk")
    assert result["status"] == "sources_cached"
    with pytest.raises(ValueError, match="official"):
        lab.research("risk", market="us", source_url="https://example.com/")


def test_reference_cache_idempotent_and_tools_do_not_place_orders(tmp_path):
    tools = ToolRegistry()
    lab = register_trading_tools(tools, tmp_path, None)
    first = lab.knowledge()
    second = lab.knowledge()
    assert [n["knowledge_id"] for n in first["notes"]] == [n["knowledge_id"] for n in second["notes"]]
    assert set(tools.tools) == {"trading_knowledge", "market_research", "trading_backtest", "trading_scope", "crypto_daily_history",
                                "paper_portfolio", "paper_order", "paper_history", "trading_chart_observe", "trading_chart_history"}
    assert all(tools.get(name).risk == "read" for name in
               ("trading_knowledge", "market_research", "trading_backtest", "trading_scope", "paper_history",
                "trading_chart_observe", "trading_chart_history"))
    assert all(tools.get(name).risk == "write" for name in
               ("crypto_daily_history", "paper_portfolio", "paper_order"))
    assert is_trading_request("Backtest my trading strategy")
    assert not is_trading_request("Tell me a bedtime story")


def test_crypto_fractional_quantity_is_modeled():
    data = bars(3)
    for bar in data:
        bar.update(open=100, high=100, low=100, close=100)
    result = _simulate(data, [True] * 3, 0, 3, 50, 0, 0, 1, quantity_step=0.01)
    assert result["orders"][0]["shares"] == pytest.approx(0.5)
    assert result["final_equity"] == pytest.approx(50)
    equity = _simulate(data, [True] * 3, 0, 3, 50, 0, 0, 1)
    assert equity["order_count"] == 0


def test_futures_cannot_silently_use_spot_accounting(tmp_path):
    with pytest.raises(ValueError, match="Futures"):
        backtest_daily(bars(), fast=2, slow=4, instrument_type="futures")
    lab = TradingLab(tmp_path)
    with pytest.raises(ValueError, match="Futures/perpetual"):
        lab.backtest("does-not-exist.csv", instrument_type="futures")
    assert lab.scope()["futures_simulator_ready"] is False
    assert "crypto_spot" in lab.scope()["simulation_instruments"]


def test_crypto_sources_and_task_routing(tmp_path):
    assert TradingLab._allowed("https://docs.kraken.com/api-reference/market-data/get-ohlc-data", ("kraken.com",))
    assert TradingLab._allowed("https://www.cftc.gov/LearnAndProtect/", ("cftc.gov",))
    assert is_trading_request("Research Bitcoin")
    assert is_trading_request("Test futures strategies")


def test_paper_ledger_initialization_fills_and_retry_are_persistent(tmp_path):
    from alice.finance.paper_trading import PaperTrading
    paper = PaperTrading(tmp_path)
    missing = paper.portfolio(currency="INR")
    assert missing["exists"] is False and missing["simulation_only"] is True
    with pytest.raises(ValueError, match="not initialized"):
        paper.order(side="buy", symbol="RELIANCE", quantity=1, reference_price=100,
                    currency="INR", idempotency_key="buy-order-001")
    paper.portfolio(action="initialize", currency="INR", starting_cash=10000)
    buy = paper.order(side="buy", symbol="RELIANCE", quantity=10, reference_price=100,
                      currency="INR", idempotency_key="buy-order-001")
    assert buy["simulation_only"] and buy["cash_after"] < 9000
    retry = paper.order(side="buy", symbol="RELIANCE", quantity=10, reference_price=100,
                        currency="INR", idempotency_key="buy-order-001")
    assert retry["duplicate_retry"] is True
    with pytest.raises(ValueError, match="different order"):
        paper.order(side="buy", symbol="RELIANCE", quantity=11, reference_price=100,
                    currency="INR", idempotency_key="buy-order-001")
    assert paper.portfolio(currency="INR")["positions"][0]["quantity"] == 10
    with pytest.raises(ValueError, match="never resets"):
        paper.portfolio(action="initialize", currency="INR", starting_cash=50000)
    sell = paper.order(side="sell", symbol="RELIANCE", quantity=4, reference_price=110,
                       currency="INR", idempotency_key="sell-order-001")
    assert sell["position_after"]["quantity"] == 6
    assert paper.history(currency="INR")["orders"]


@pytest.mark.parametrize("kwargs, message", [
    ({"instrument_type": "futures"}, "futures/perpetuals"),
    ({"quantity": 0.5, "instrument_type": "equity"}, "whole shares"),
    ({"idempotency_key": ""}, "idempotency_key"),
])
def test_paper_ledger_rejects_unsafe_or_ambiguous_order(tmp_path, kwargs, message):
    from alice.finance.paper_trading import PaperTrading
    paper = PaperTrading(tmp_path)
    paper.portfolio(action="initialize", starting_cash=1000)
    values = {"side": "buy", "symbol": "ABC", "quantity": 1,
              "reference_price": 10, "idempotency_key": "order-key-0001"}
    values.update(kwargs)
    with pytest.raises(ValueError, match=message):
        paper.order(**values)


def test_paper_order_rejects_insufficient_cash_and_oversell(tmp_path):
    from alice.finance.paper_trading import PaperTrading
    paper = PaperTrading(tmp_path)
    paper.portfolio(action="initialize", starting_cash=100)
    with pytest.raises(ValueError, match="Insufficient"):
        paper.order(side="buy", symbol="ABC", quantity=20, reference_price=10,
                    idempotency_key="order-key-0001")
    with pytest.raises(ValueError, match="only 0"):
        paper.order(side="sell", symbol="ABC", quantity=1, reference_price=10,
                    idempotency_key="order-key-0002")


def test_paper_tools_are_selected_and_brain_policy_keeps_them_simulation_only(tmp_path):
    from alice.agent.planner import Planner
    from alice.agent.tool_selection import select_tools
    registry = ToolRegistry()
    for index in range(24):
        registry.add(f"unrelated_tool_{index}", "Unrelated utility", lambda: None)
    register_trading_tools(registry, tmp_path, None)
    selected = select_tools("Paper trade 2 shares of ABC at a supplied price", registry)
    assert "paper_order" in selected
    assert "paper_portfolio" in selected
    policy = Planner._system_for({"paper_order", "paper_portfolio"})
    assert "never brokerage orders" in policy
    assert "idempotency keys" in policy


def test_chart_watch_requests_enter_tool_path_and_select_visual_observer():
    from alice.ui.app import AliceUI
    from alice.agent.tool_selection import select_tools
    registry = ToolRegistry()
    registry.add("trading_chart_observe", "Capture and inspect current screen chart candles", lambda: None)
    registry.add("trading_chart_history", "Read saved visual chart observations", lambda: None)
    request = "Watch this chart and track how the candles are moving."
    assert is_trading_request(request)
    assert AliceUI._needs_tools(request)
    assert "trading_chart_observe" in select_tools(request, registry)


def test_chart_observation_is_persisted_as_unverified_visual_evidence(tmp_path):
    from alice.finance.service import TradingLab
    lab = TradingLab(tmp_path)
    screenshot = tmp_path / "chart.png"
    screenshot.write_bytes(b"screen")
    lab.chart_analyzer = lambda prompt: {
        "observation_id": "vision-test-1", "summary": "A chart is visible; symbol unknown.",
        "extracted_text": "15m", "claims": [], "warnings": ["Candles are too small to read."],
        "reliability": {"confidence": 0.35},
        "evidence": {"path": str(screenshot), "content_hash": __import__("hashlib").sha256(b"screen").hexdigest()},
    }
    observed = lab.observe_chart()
    assert observed["status"] == "visual_observation_unverified"
    assert observed["warnings"]
    assert lab.paper.chart_history()["observations"][0]["summary"] == observed["summary"]


def test_combined_asset_search_stays_within_existing_search_limit(tmp_path):
    class Search:
        def search(self, query, max_results):
            assert len(query) <= 500
            assert "site:cftc.gov" in query and "site:nseindia.com" in query
            return {"results": []}
    assert TradingLab(tmp_path, Search()).research("x" * 300, market="all")["status"] == "no_sources"


def test_ui_trading_requests_reach_tools():
    from alice.ui.app import AliceUI
    assert AliceUI._needs_tools("Backtest my trading strategy")
    assert AliceUI._needs_tools("Get market research from primary sources")
    assert not AliceUI._needs_tools("Tell me a bedtime story")


def test_fetch_rejects_redirects_and_bounds_bytes(monkeypatch):
    import requests
    class Reply:
        status_code = 302
        headers = {"Content-Type": "text/html"}
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def raise_for_status(self): pass
        def iter_content(self, chunk_size): yield b"x" * 262145
    reply = Reply()
    calls = []
    def get(url, **kwargs):
        calls.append(kwargs)
        return reply
    monkeypatch.setattr(requests, "get", get)
    with pytest.raises(ValueError, match="Redirects"):
        TradingLab._fetch("https://www.nseindia.com/all-reports")
    assert calls[0]["allow_redirects"] is False
    reply.status_code = 200
    with pytest.raises(ValueError, match="256 KiB"):
        TradingLab._fetch("https://www.nseindia.com/all-reports")
