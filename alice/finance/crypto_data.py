"""Bounded, public, completed daily spot candles; no authenticated endpoints."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from alice.core.atomic_json import atomic_write_json
from alice.execution.postconditions import PostconditionResult
from .backtest import load_daily_csv


class KrakenDailyHistory:
    URL = "https://api.kraken.com/0/public/OHLC"
    PAIRS = {
        "BTC/USD": ("XBTUSD", {"XXBTZUSD", "XBTUSD", "BTC/USD"}),
        "ETH/USD": ("ETHUSD", {"XETHZUSD", "ETHUSD", "ETH/USD"}),
    }

    def __init__(self, workspace):
        self.workspace = Path(workspace).resolve()

    @classmethod
    def _pair(cls, pair):
        pair = str(pair).strip().upper()
        if pair not in cls.PAIRS:
            raise ValueError("Supported spot pairs are BTC/USD and ETH/USD")
        return pair

    def _request(self, pair):
        import requests
        with requests.get(self.URL, params={"pair": self.PAIRS[pair][0], "interval": 1440},
                          timeout=(5, 15), allow_redirects=False, stream=True) as response:
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError("Unexpected public data response")
            payload = bytearray()
            for chunk in response.iter_content(chunk_size=8192):
                payload.extend(chunk)
                if len(payload) > 1048576:
                    raise ValueError("Public data response exceeds 1 MiB")
        return json.loads(payload)

    def download(self, pair="BTC/USD"):
        pair = self._pair(pair)
        payload = self._request(pair)
        if payload.get("error"):
            raise ValueError("The public market-data provider returned an error")
        result = payload.get("result", {})
        keys = [key for key in result if key != "last"]
        if len(keys) != 1 or keys[0] not in self.PAIRS[pair][1]:
            raise ValueError("Provider returned an unexpected spot pair")
        candles = result[keys[0]]
        if not isinstance(candles, list) or not 2 <= len(candles) <= 1000:
            raise ValueError("Expected a bounded recent candle array")
        rows = []
        today = datetime.now(timezone.utc).date()
        # Kraken always includes a current, uncommitted final candle, even when
        # 'since' is specified. It must never become historical test evidence.
        # Some live responses include 721 entries despite the documented limit.
        # Keep a fixed cache budget after dropping the uncommitted final candle.
        for row in candles[:-1][-719:]:
            if not isinstance(row, list) or len(row) < 8:
                raise ValueError("Malformed daily candle")
            stamp = datetime.fromtimestamp(int(row[0]), timezone.utc)
            if stamp.hour or stamp.minute or stamp.second:
                raise ValueError("Expected UTC daily boundaries")
            if stamp.date() >= today:
                continue
            rows.append({"date": stamp.date().isoformat(), "open": row[1], "high": row[2],
                         "low": row[3], "close": row[4], "volume": row[6], "symbol": pair})
        if len(rows) < 50:
            raise ValueError("Insufficient completed daily spot data")
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=["date", "open", "high", "low", "close", "volume", "symbol"])
        writer.writeheader()
        writer.writerows(rows)
        content = stream.getvalue().encode("utf-8")
        digest = hashlib.sha256(content).hexdigest()
        directory = (self.workspace / "market" / "crypto").resolve()
        if not directory.is_relative_to(self.workspace):
            raise ValueError("Crypto dataset directory leaves ALICE's workspace")
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / (pair.replace("/", "_") + "_daily_" + digest[:16] + ".csv")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=directory, suffix=".csv", delete=False) as out:
                temporary = Path(out.name)
                out.write(content)
                out.flush()
                os.fsync(out.fileno())
            checked, actual_hash = load_daily_csv(temporary)
            if actual_hash != digest:
                raise ValueError("Dataset changed before caching")
            os.replace(temporary, target)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        metadata = {
            "provider": "Kraken public spot OHLC", "pair": pair, "source_url": self.URL,
            "retrieved_at": datetime.now(timezone.utc).isoformat(), "interval": "1d", "timezone": "UTC",
            "instrument_type": "crypto_spot", "currency": "USD", "sha256": digest,
            "rows": len(checked), "first_date": checked[0]["date"].isoformat(),
            "last_date": checked[-1]["date"].isoformat(), "current_candle_excluded": True,
            "provider_returned_candles": len(candles),
            "source_accuracy_independently_verified": False,
            "limitations": ["At most 719 recent completed daily bars; not full exchange history.",
                            "Venue-specific historical candles; not executable quotes.",
                            "No perpetuals, futures, funding, staking, custody or order-book simulation."],
        }
        atomic_write_json(target.with_suffix(".json"), metadata)
        return {"ok": True, "status": "downloaded", "dataset_csv": str(target.relative_to(self.workspace)),
                "metadata_path": str(target.with_suffix(".json").relative_to(self.workspace)), **metadata}

    def verify(self, args, result):
        try:
            if not isinstance(result, dict) or not result.get("ok"):
                raise ValueError("Download failed")
            pair = self._pair(args.get("pair", "BTC/USD"))
            target = (self.workspace / result["dataset_csv"]).resolve()
            meta_path = (self.workspace / result["metadata_path"]).resolve()
            if not target.is_relative_to(self.workspace) or not meta_path.is_relative_to(self.workspace):
                raise ValueError("Invalid dataset location")
            if target.suffix != ".csv" or meta_path != target.with_suffix(".json"):
                raise ValueError("Dataset/metadata paths do not match")
            checked, digest = load_daily_csv(target)
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            if (metadata.get("pair") != pair or metadata.get("instrument_type") != "crypto_spot"
                    or metadata.get("source_url") != self.URL or metadata.get("sha256") != digest
                    or result.get("sha256") != digest or metadata.get("rows") != len(checked)
                    or not 50 <= len(checked) <= 719
                    or checked[-1]["date"] >= datetime.now(timezone.utc).date()):
                raise ValueError("Dataset metadata failed independent readback")
            return PostconditionResult(True, {"observed": True, "dataset_sha256": digest,
                "pair": pair, "rows": len(checked), "last_date": checked[-1]["date"].isoformat(),
                "source_accuracy_verified": False}, "Local historical cache and hash re-read; market accuracy is not cross-verified.")
        except Exception as exc:
            return PostconditionResult(False, {"observed": False}, "dataset_verification_failed:" + type(exc).__name__)
