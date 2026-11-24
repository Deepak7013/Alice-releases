"""Persistent, simulation-only paper portfolio and fill ledger.

Orders use a price supplied by the caller, then apply explicit fee/slippage
assumptions. This module has no broker or live-order integration.
"""
from __future__ import annotations

import hashlib
import math
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


_ASSETS = {"equity", "etf", "crypto_spot"}
_ACCOUNT = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_SYMBOL = re.compile(r"^[A-Za-z0-9._:/-]{1,40}$")


def _finite(value, label, minimum, maximum):
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return number


class PaperTrading:
    """A local paper account; writes are simulated ledger entries only."""

    def __init__(self, root):
        root = Path(root).resolve()
        self.path = root / "alice_workspace" / "finance" / "paper_trading.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS accounts (
                    account TEXT NOT NULL, currency TEXT NOT NULL,
                    starting_cash REAL NOT NULL, cash REAL NOT NULL,
                    created_at TEXT NOT NULL, PRIMARY KEY(account, currency)
                );
                CREATE TABLE IF NOT EXISTS positions (
                    account TEXT NOT NULL, currency TEXT NOT NULL,
                    symbol TEXT NOT NULL, instrument_type TEXT NOT NULL,
                    quantity REAL NOT NULL, average_cost REAL NOT NULL,
                    realized_pnl REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY(account, currency, symbol, instrument_type)
                );
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY, account TEXT NOT NULL,
                    currency TEXT NOT NULL, idempotency_key TEXT NOT NULL,
                    side TEXT NOT NULL, symbol TEXT NOT NULL,
                    instrument_type TEXT NOT NULL, quantity REAL NOT NULL,
                    reference_price REAL NOT NULL, fill_price REAL NOT NULL,
                    fee REAL NOT NULL, slippage_cost REAL NOT NULL,
                    realized_pnl REAL NOT NULL, note TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(account, currency, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS chart_observations (
                    observation_id TEXT PRIMARY KEY, captured_at TEXT NOT NULL,
                    screenshot_path TEXT NOT NULL, screenshot_sha256 TEXT NOT NULL,
                    summary TEXT NOT NULL, extracted_text TEXT NOT NULL,
                    warnings_json TEXT NOT NULL, confidence REAL NOT NULL,
                    payload_json TEXT NOT NULL
                );
            """)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @contextmanager
    def _db(self):
        db = self._connect()
        try:
            with db:
                yield db
        finally:
            db.close()

    def portfolio(self, action="view", account="default", currency="USD", starting_cash=None):
        account = str(account).strip()
        currency = str(currency).strip().upper()
        if not _ACCOUNT.fullmatch(account):
            raise ValueError("account must be 1–40 letters, digits, _ or -")
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("currency must be a three-letter code such as USD or INR")
        if action not in {"view", "initialize"}:
            raise ValueError("action must be view or initialize")
        with self._db() as db:
            row = db.execute("SELECT * FROM accounts WHERE account=? AND currency=?", (account, currency)).fetchone()
            if action == "initialize":
                if row:
                    raise ValueError("This paper account already exists; initialization never resets or adds cash")
                cash = _finite(starting_cash, "starting_cash", 1, 1e12)
                db.execute("INSERT INTO accounts VALUES (?, ?, ?, ?, ?)",
                           (account, currency, cash, cash, datetime.now(timezone.utc).isoformat()))
                row = db.execute("SELECT * FROM accounts WHERE account=? AND currency=?", (account, currency)).fetchone()
            elif not row:
                return {"ok": True, "simulation_only": True, "exists": False,
                        "account": account, "currency": currency,
                        "message": "Initialize explicitly with a starting_cash amount before placing simulated orders."}
            positions = [dict(p) for p in db.execute(
                "SELECT symbol,instrument_type,quantity,average_cost,realized_pnl FROM positions "
                "WHERE account=? AND currency=? AND ABS(quantity)>1e-12 ORDER BY symbol",
                (account, currency)).fetchall()]
            return {"ok": True, "simulation_only": True, "exists": True,
                    "account": account, "currency": currency, "starting_cash": row["starting_cash"],
                    "cash": row["cash"], "positions": positions,
                    "ledger_path": str(self.path),
                    "note": "Local simulation only. No live quotes, brokerage, or real orders."}

    def order(self, account="default", side="", symbol="", instrument_type="equity",
              quantity=None, reference_price=None, currency="USD", idempotency_key="",
              fee_bps=10, slippage_bps=5, note=""):
        account, currency = str(account).strip(), str(currency).strip().upper()
        side, symbol, instrument_type = str(side).strip().lower(), str(symbol).strip().upper(), str(instrument_type).strip().lower()
        key = str(idempotency_key).strip()
        if not _ACCOUNT.fullmatch(account):
            raise ValueError("Invalid account name")
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("currency must be a three-letter code such as USD or INR")
        if side not in {"buy", "sell"}:
            raise ValueError("side must be buy or sell")
        if not _SYMBOL.fullmatch(symbol):
            raise ValueError("Provide one symbol or pair, not a free-form name")
        if instrument_type not in _ASSETS:
            raise ValueError("Paper ledger supports equity, etf, and crypto_spot only; futures/perpetuals are excluded")
        if len(key) < 8 or len(key) > 100:
            raise ValueError("Provide a unique idempotency_key (8–100 characters) so retries cannot duplicate an order")
        if len(str(note)) > 300:
            raise ValueError("note is limited to 300 characters")
        qty = _finite(quantity, "quantity", 1e-8, 1e9)
        price = _finite(reference_price, "reference_price", 1e-8, 1e12)
        fee_rate = _finite(fee_bps, "fee_bps", 0, 1000) / 10000
        slip_rate = _finite(slippage_bps, "slippage_bps", 0, 1000) / 10000
        # Equity/ETF quantities are whole shares. Crypto stays fractional.
        if instrument_type != "crypto_spot" and abs(qty - round(qty)) > 1e-9:
            raise ValueError("equity and ETF paper quantities must be whole shares")
        fill = price * (1 + slip_rate if side == "buy" else 1 - slip_rate)
        gross, fee = qty * fill, qty * fill * fee_rate
        now = datetime.now(timezone.utc).isoformat()
        order_id = hashlib.sha256(f"{account}|{currency}|{key}".encode()).hexdigest()[:20]
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            duplicate = db.execute("SELECT * FROM orders WHERE account=? AND currency=? AND idempotency_key=?",
                                   (account, currency, key)).fetchone()
            if duplicate:
                same_request = (
                    duplicate["side"] == side and duplicate["symbol"] == symbol
                    and duplicate["instrument_type"] == instrument_type
                    and math.isclose(duplicate["quantity"], qty, rel_tol=0, abs_tol=1e-12)
                    and math.isclose(duplicate["reference_price"], price, rel_tol=0, abs_tol=1e-12)
                    and math.isclose(duplicate["fee"], gross * fee_rate, rel_tol=0, abs_tol=1e-10)
                    and math.isclose(duplicate["slippage_cost"], qty * abs(fill - price), rel_tol=0, abs_tol=1e-10)
                )
                if not same_request:
                    raise ValueError("This idempotency_key belongs to a different order; use a fresh key for a new simulated order")
                result = dict(duplicate)
                result.update(ok=True, simulation_only=True, duplicate_retry=True,
                              message="The idempotency key was already processed; no second ledger change was made.")
                return result
            acct = db.execute("SELECT * FROM accounts WHERE account=? AND currency=?", (account, currency)).fetchone()
            if not acct:
                raise ValueError("Paper account is not initialized. Call paper_portfolio(action='initialize', starting_cash=..., currency=...) first.")
            pos = db.execute("SELECT * FROM positions WHERE account=? AND currency=? AND symbol=? AND instrument_type=?",
                             (account, currency, symbol, instrument_type)).fetchone()
            held = pos["quantity"] if pos else 0.0
            realized = 0.0
            if side == "buy":
                debit = gross + fee
                if debit > acct["cash"] + 1e-8:
                    raise ValueError("Insufficient paper cash for this simulated fill")
                new_qty = held + qty
                avg_cost = ((held * pos["average_cost"] if pos else 0) + debit) / new_qty
                cash_delta = -debit
            else:
                if qty > held + 1e-8:
                    raise ValueError(f"Cannot paper-sell {qty:g}; only {held:g} is held")
                proceeds = gross - fee
                avg_cost = pos["average_cost"]
                realized = proceeds - qty * avg_cost
                new_qty = max(0.0, held - qty)
                cash_delta = proceeds
            db.execute("UPDATE accounts SET cash=cash+? WHERE account=? AND currency=?", (cash_delta, account, currency))
            db.execute("""INSERT INTO positions VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(account,currency,symbol,instrument_type) DO UPDATE SET
                       quantity=excluded.quantity, average_cost=excluded.average_cost,
                       realized_pnl=positions.realized_pnl+excluded.realized_pnl""",
                       (account, currency, symbol, instrument_type, new_qty, avg_cost, realized))
            slippage_cost = qty * abs(fill - price)
            values = (order_id, account, currency, key, side, symbol, instrument_type, qty,
                      price, fill, fee, slippage_cost, realized, str(note), now)
            db.execute("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", values)
            position = db.execute("SELECT quantity,average_cost,realized_pnl FROM positions WHERE account=? AND currency=? AND symbol=? AND instrument_type=?",
                                  (account, currency, symbol, instrument_type)).fetchone()
            updated = db.execute("SELECT cash FROM accounts WHERE account=? AND currency=?", (account, currency)).fetchone()
            return {"ok": True, "simulation_only": True, "duplicate_retry": False,
                    "order_id": order_id, "account": account, "currency": currency,
                    "side": side, "symbol": symbol, "instrument_type": instrument_type,
                    "quantity": qty, "reference_price": price, "simulated_fill_price": fill,
                    "fee": fee, "slippage_cost": slippage_cost, "realized_pnl": realized,
                    "cash_after": updated["cash"], "position_after": dict(position),
                    "created_at": now, "ledger_path": str(self.path),
                    "note": "Simulated immediately at user-supplied price with configured costs; this is not a market quote or real order."}

    def history(self, account="default", currency="USD", limit=50):
        account, currency = str(account).strip(), str(currency).strip().upper()
        if not _ACCOUNT.fullmatch(account) or not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("Provide a valid account name and three-letter currency")
        if isinstance(limit, bool) or int(limit) != limit or not 1 <= int(limit) <= 200:
            raise ValueError("limit must be an integer from 1 to 200")
        with self._db() as db:
            rows = db.execute("SELECT order_id,side,symbol,instrument_type,quantity,reference_price,fill_price,fee,slippage_cost,realized_pnl,note,created_at FROM orders WHERE account=? AND currency=? ORDER BY rowid DESC LIMIT ?",
                              (account, currency, int(limit))).fetchall()
        return {"ok": True, "simulation_only": True, "account": account,
                "currency": currency, "orders": [dict(row) for row in rows],
                "ledger_path": str(self.path)}

    def save_chart_observation(self, payload):
        """Persist a chart screenshot interpretation as uncertain evidence, not market data."""
        import json
        from pathlib import Path
        if not isinstance(payload, dict) or not payload.get("evidence"):
            raise ValueError("Vision result must include screenshot evidence metadata")
        evidence = payload["evidence"]
        image = Path(str(evidence.get("path", "")))
        if not image.is_file():
            raise ValueError("Captured screenshot is missing; observation was not saved")
        digest = str(evidence.get("sha256", evidence.get("content_hash", "")))
        if not re.fullmatch(r"[a-fA-F0-9]{64}", digest):
            raise ValueError("Screenshot hash is missing or invalid")
        actual_digest = hashlib.sha256(image.read_bytes()).hexdigest()
        if actual_digest.casefold() != digest.casefold():
            raise ValueError("Captured screenshot hash changed; observation was not saved")
        observation_id = hashlib.sha256((digest + str(payload.get("observation_id", ""))).encode()).hexdigest()[:20]
        warnings = payload.get("warnings", [])
        if not isinstance(warnings, list):
            warnings = ["Vision returned warnings in an unsupported format"]
        confidence = 0.0
        reliability = payload.get("reliability", {})
        if isinstance(reliability, dict):
            try:
                confidence = min(1.0, max(0.0, float(reliability.get("confidence", 0))))
            except (TypeError, ValueError):
                confidence = 0.0
        captured_at = datetime.now(timezone.utc).isoformat()
        safe = {"observation_id": observation_id, "captured_at": captured_at,
                "evidence": evidence, "summary": str(payload.get("summary", ""))[:10000],
                "extracted_text": str(payload.get("extracted_text", ""))[:20000],
                "claims": payload.get("claims", [])[:30] if isinstance(payload.get("claims"), list) else [],
                "warnings": [str(value)[:1000] for value in warnings[:30]],
                "reliability": reliability, "status": "visual_observation_unverified"}
        with self._db() as db:
            db.execute("INSERT OR IGNORE INTO chart_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (observation_id, captured_at, str(image.resolve()), digest,
                        safe["summary"], safe["extracted_text"], json.dumps(safe["warnings"]),
                        confidence, json.dumps(safe, ensure_ascii=False)))
        return {"ok": True, "simulation_only": True, **safe,
                "note": "This is an uncertain visual reading, not verified OHLC data or a trading signal. Compare against timestamped market data."}

    def chart_history(self, limit=50):
        if isinstance(limit, bool) or int(limit) != limit or not 1 <= int(limit) <= 200:
            raise ValueError("limit must be an integer from 1 to 200")
        import json
        with self._db() as db:
            rows = db.execute("SELECT payload_json FROM chart_observations ORDER BY rowid DESC LIMIT ?",
                              (int(limit),)).fetchall()
        return {"ok": True, "observations": [json.loads(row[0]) for row in rows],
                "note": "Visual chart observations are unverified evidence, not prices or signals."}

