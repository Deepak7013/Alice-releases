"""Deterministic, long-only daily-bar simulations. No brokerage integration."""
from __future__ import annotations

import csv
import hashlib
import io
import math
from datetime import date
from decimal import Decimal, ROUND_FLOOR


def _number(value, name, *, minimum=0.0, maximum=float("inf")):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {name}") from exc
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValueError(f"Invalid {name}")
    return result


def load_daily_csv(path):
    """Reject ambiguous data rather than silently sorting, filling, or adjusting it."""
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("CSV exceeds the 20 MiB limit")
    raw = path.read_bytes()
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    names = [str(name).strip().lower() for name in (reader.fieldnames or [])]
    if len(set(names)) != len(names) or not {"date", "open", "high", "low", "close"}.issubset(names):
        raise ValueError("CSV requires unique date,open,high,low,close columns")
    reader.fieldnames = names
    bars = []
    symbol = None
    for row in reader:
        if len(bars) >= 50000:
            raise ValueError("CSV exceeds 50,000 daily bars")
        stamp = date.fromisoformat(str(row.get("date", "")).strip())
        if bars and stamp <= bars[-1]["date"]:
            raise ValueError("Dates must be unique and strictly increasing")
        if "symbol" in row:
            current_symbol = str(row["symbol"]).strip()
            if not current_symbol or (symbol is not None and current_symbol != symbol):
                raise ValueError("CSV must contain exactly one security")
            symbol = current_symbol
        bar = {name: _number(row.get(name), name, minimum=1e-12, maximum=1e12)
               for name in ("open", "high", "low", "close")}
        if not bar["low"] <= min(bar["open"], bar["close"]) <= max(bar["open"], bar["close"]) <= bar["high"]:
            raise ValueError(f"Inconsistent OHLC prices at {stamp}")
        if "volume" in row and str(row["volume"]).strip():
            bar["volume"] = _number(row["volume"], "volume")
        bar["date"] = stamp
        bars.append(bar)
    if not bars:
        raise ValueError("CSV is empty")
    return bars, hashlib.sha256(raw).hexdigest()


def _simulate(bars, signals, start, stop, capital, fee_bps, slippage_bps, allocation, quantity_step=1.0):
    cash, shares, entry_cost = capital, 0, 0.0
    fee_rate, slip = fee_bps / 10000, slippage_bps / 10000
    fees = slippage_cost = 0.0
    orders, profits, equity = [], [], []

    def order(index, side, reference, *, terminal=False):
        nonlocal cash, shares, fees, slippage_cost, entry_cost
        fill = reference * (1 + slip if side == "buy" else 1 - slip)
        if side == "buy":
            step = Decimal(str(quantity_step))
            budget = Decimal(str(cash)) * Decimal(str(allocation))
            unit_cost = Decimal(str(fill)) * (1 + Decimal(str(fee_rate)))
            units = (budget / (unit_cost * step)).to_integral_value(rounding=ROUND_FLOOR)
            amount = float(units * step)
        else:
            amount = shares
        if amount <= 0:
            return
        gross = amount * fill
        commission = gross * fee_rate
        fees += commission
        slippage_cost += amount * abs(fill - reference)
        if side == "buy":
            entry_cost = gross + commission
            cash -= entry_cost
            shares = amount
        else:
            proceeds = gross - commission
            cash += proceeds
            profits.append(proceeds - entry_cost)
            shares = 0
        orders.append({"date": bars[index]["date"].isoformat(), "side": side,
                       "shares": amount, "reference_price": reference,
                       "fill_price": fill, "fee": commission,
                       "terminal_liquidation": terminal})

    for i in range(start, stop):
        if signals[i] and not shares:
            order(i, "buy", bars[i]["open"])
        elif not signals[i] and shares:
            order(i, "sell", bars[i]["open"])
        equity.append(cash + shares * bars[i]["close"])
    if shares:
        order(stop - 1, "sell", bars[stop - 1]["close"], terminal=True)
        equity[-1] = cash
    peak, drawdown = capital, 0.0
    for value in equity:
        peak = max(peak, value)
        drawdown = max(drawdown, (peak - value) / peak)
    stride = max(1, math.ceil(len(equity) / 80))
    points = list(range(0, len(equity), stride))
    if points[-1] != len(equity) - 1:
        points.append(len(equity) - 1)
    return {
        "start": bars[start]["date"].isoformat(), "end": bars[stop - 1]["date"].isoformat(),
        "bars": stop - start, "initial_capital": capital, "final_equity": cash,
        "net_profit": cash - capital, "return_pct": (cash / capital - 1) * 100,
        "max_drawdown_pct": drawdown * 100, "fees_paid": fees,
        "slippage_cost": slippage_cost, "order_count": len(orders),
        "closed_trades": len(profits),
        "win_rate_pct": 100 * sum(p > 0 for p in profits) / len(profits) if profits else None,
        "orders": orders[:100], "orders_truncated": len(orders) > 100,
        "equity_sample": [{"date": bars[start + i]["date"].isoformat(), "equity": equity[i]} for i in points],
    }


def backtest_daily(bars, *, fast=10, slow=30, capital=100000,
                   fee_bps=10, slippage_bps=5, allocation=1.0, test_fraction=0.3,
                   instrument_type="equity", quantity_step=None):
    """Signals use prior closes, with fills at the next bar's open.

    Parameters are fixed by the caller, never selected using the test segment.
    Each segment starts with cash; earlier bars are used only for indicator warmup.
    """
    if instrument_type not in {"equity", "etf", "crypto_spot"}:
        raise ValueError("This simulator supports equity, etf and crypto_spot only. Futures need a separate contract, expiry, roll, margin and settlement model.")
    quantity_step = (1e-8 if instrument_type == "crypto_spot" else 1) if quantity_step is None else quantity_step
    quantity_step = _number(quantity_step, "quantity_step", minimum=1e-8, maximum=1)
    if instrument_type != "crypto_spot" and quantity_step != 1:
        raise ValueError("Equity/ETF simulations use whole shares")
    if isinstance(fast, bool) or isinstance(slow, bool) or int(fast) != fast or int(slow) != slow:
        raise ValueError("fast and slow must be integers")
    fast, slow = int(fast), int(slow)
    if not 1 <= fast < slow <= 500:
        raise ValueError("Require 1 <= fast < slow <= 500")
    capital = _number(capital, "capital", minimum=1, maximum=1e12)
    fee_bps = _number(fee_bps, "fee_bps", maximum=1000)
    slippage_bps = _number(slippage_bps, "slippage_bps", maximum=1000)
    allocation = _number(allocation, "allocation", minimum=0.001, maximum=1)
    test_fraction = _number(test_fraction, "test_fraction", minimum=0.1, maximum=0.5)
    split = int(len(bars) * (1 - test_fraction))
    if split - slow < 5 or len(bars) - split < 5:
        raise ValueError("Need at least five training and five test bars after indicator warmup")
    prefix = [0.0]
    for bar in bars:
        prefix.append(prefix[-1] + bar["close"])
    signals = [False] * len(bars)
    for i in range(slow, len(bars)):
        short_mean = (prefix[i] - prefix[i - fast]) / fast
        long_mean = (prefix[i] - prefix[i - slow]) / slow
        signals[i] = short_mean > long_mean
    options = (capital, fee_bps, slippage_bps, allocation, quantity_step)
    training = _simulate(bars, signals, slow, split, *options)
    testing = _simulate(bars, signals, split, len(bars), *options)
    benchmark = _simulate(bars, [True] * len(bars), split, len(bars),
                          capital, fee_bps, slippage_bps, 1.0, quantity_step)
    return {
        "simulation_only": True, "strategy": "long_only_sma_crossover", "instrument_type": instrument_type,
        "parameters": {"fast": fast, "slow": slow, "capital": capital,
                       "fee_bps_per_side": fee_bps, "slippage_bps_per_side": slippage_bps,
                       "entry_allocation_fraction": allocation, "test_fraction": test_fraction,
                       "quantity_step": quantity_step},
        "training_period": training, "test_period": testing,
        "buy_and_hold_same_test_period": benchmark,
        "test_excess_return_percentage_points": testing["return_pct"] - benchmark["return_pct"],
        "assumptions": ["Daily bars; prior-close signals filled at next available session open.",
                        f"Quantity step={quantity_step}; long only, no leverage or short selling; entry allocation may drift with prices.",
                        "Assumed bps fees and slippage apply per side; final positions liquidated at last close with costs.",
                        "Test period is a chronological holdout, not proof it was never inspected or retuned by the user."],
        "limitations": ["No market calendar, spreads, fill volume limits, tax schedule, dividends or interest modeled.",
                        "Fees are assumptions, not a verified broker or exchange tariff.",
                        "Single supplied security: survivorship bias and corporate actions require separate validation.",
                        "Historical simulation does not establish future profitability or readiness for live trading.",
                        "For crypto: no derivatives, perpetual funding, custody, venue outage, staking or liquidation model. Quantity step is a simulation assumption, not a verified venue rule."],
    }
