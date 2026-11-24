import copy
import json
from datetime import datetime, timedelta, timezone

import pytest

from alice.execution.postconditions import PostconditionRegistry
from alice.finance import TradingLab, register_trading_tools
from alice.finance.crypto_data import KrakenDailyHistory
from alice.tools.registry import ToolRegistry


def payload():
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = []
    for i in range(61):
        stamp = int((today - timedelta(days=60 - i)).timestamp())
        price = 60000 + i * 10
        rows.append([stamp, str(price), str(price + 5), str(price - 5), str(price), str(price), "2.5", 20])
    return {"error": [], "result": {"XXBTZUSD": rows, "last": rows[-1][0]}}


def make(tmp_path, monkeypatch):
    lab = TradingLab(tmp_path)
    monkeypatch.setattr(lab.crypto_data, "_request", lambda pair: payload())
    return lab


def test_completed_candles_cached_with_provenance_and_verified(tmp_path, monkeypatch):
    lab = make(tmp_path, monkeypatch)
    result = lab.crypto_data.download()
    assert result["rows"] == 60
    assert result["last_date"] < datetime.now(timezone.utc).date().isoformat()
    assert result["current_candle_excluded"] is True
    assert result["currency"] == "USD"
    assert not result["source_accuracy_independently_verified"]
    evidence = lab.crypto_data.verify({"pair": "BTC/USD"}, result)
    assert evidence.ok and evidence.evidence["observed"]
    report = lab.backtest(result["dataset_csv"], fast=2, slow=4,
                          instrument_type="crypto_spot", capital=1000)
    assert report["dataset"]["currency"] == "USD"
    assert report["test_period"]["orders"][0]["shares"] < 1


def test_metadata_prevents_wrong_instrument_or_currency(tmp_path, monkeypatch):
    lab = make(tmp_path, monkeypatch)
    result = lab.crypto_data.download()
    with pytest.raises(ValueError, match="instrument_type"):
        lab.backtest(result["dataset_csv"])
    with pytest.raises(ValueError, match="Currency"):
        lab.backtest(result["dataset_csv"], instrument_type="crypto_spot", currency="INR")


def test_tampered_cache_cannot_be_verified_or_backtested(tmp_path, monkeypatch):
    lab = make(tmp_path, monkeypatch)
    result = lab.crypto_data.download()
    target = lab.workspace / result["dataset_csv"]
    with target.open("ab") as stream:
        stream.write(b"\n")
    assert not lab.crypto_data.verify({}, result).ok
    with pytest.raises(ValueError, match="hash"):
        lab.backtest(result["dataset_csv"], instrument_type="crypto_spot")


def test_wrong_pair_and_provider_errors_are_rejected(tmp_path, monkeypatch):
    downloader = KrakenDailyHistory(tmp_path)
    wrong = copy.deepcopy(payload())
    wrong["result"]["XETHZUSD"] = wrong["result"].pop("XXBTZUSD")
    monkeypatch.setattr(downloader, "_request", lambda pair: wrong)
    with pytest.raises(ValueError, match="unexpected spot pair"):
        downloader.download("BTC/USD")
    monkeypatch.setattr(downloader, "_request", lambda pair: {"error": ["unavailable"]})
    with pytest.raises(ValueError, match="provider returned an error"):
        downloader.download()
    with pytest.raises(ValueError, match="Supported spot pairs"):
        downloader.download("BTC-PERP")


def test_invalid_prices_are_not_promoted_to_dataset(tmp_path, monkeypatch):
    downloader = KrakenDailyHistory(tmp_path)
    bad = payload()
    bad["result"]["XXBTZUSD"][4][4] = "nan"
    monkeypatch.setattr(downloader, "_request", lambda pair: bad)
    with pytest.raises(ValueError):
        downloader.download()
    assert not list(tmp_path.rglob("*.csv"))


def test_registered_download_has_independent_cache_observer(tmp_path, monkeypatch):
    tools = ToolRegistry()
    tools.postconditions = PostconditionRegistry()
    lab = register_trading_tools(tools, tmp_path, None)
    monkeypatch.setattr(lab.crypto_data, "_request", lambda pair: payload())
    result = tools.run("crypto_daily_history", {"pair": "BTC/USD"})
    assert tools.postconditions.verify("crypto_daily_history", {"pair": "BTC/USD"}, result).ok


def test_live_721_entry_variant_is_capped_after_removing_current_candle(tmp_path, monkeypatch):
    downloader = KrakenDailyHistory(tmp_path)
    data = payload()
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = []
    for i in range(721):
        template = list(data["result"]["XXBTZUSD"][0])
        template[0] = int((today - timedelta(days=720-i)).timestamp())
        rows.append(template)
    data["result"]["XXBTZUSD"] = rows
    monkeypatch.setattr(downloader, "_request", lambda pair: data)
    result = downloader.download()
    assert result["provider_returned_candles"] == 721
    assert result["rows"] == 719
    assert result["last_date"] == (today-timedelta(days=1)).date().isoformat()
    assert downloader.verify({}, result).ok
