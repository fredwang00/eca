"""Fetch quarterly financial metrics from Yahoo Finance via yfinance."""

from __future__ import annotations

import math
from datetime import date

import yfinance as yf


def normalize_quarter_label(date_str: str | date) -> str:
    """Convert '2025-09-30' or a date object to 'Q3 2025'."""
    d = date.fromisoformat(date_str) if isinstance(date_str, str) else date_str
    quarter = (d.month - 1) // 3 + 1
    return f"Q{quarter} {d.year}"


def _safe_get(df, field: str, col) -> float | None:
    """Safely extract a value from a DataFrame, returning None for NaN/missing."""
    if df is None or df.empty or field not in df.index:
        return None
    val = df.loc[field, col]
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    return float(val)


def _to_millions(val: float | None) -> float | None:
    if val is None:
        return None
    return round(val / 1_000_000, 1)


def fetch_quarterly_metrics(ticker: str) -> dict[str, dict[str, float | None]]:
    """Fetch quarterly metrics from yfinance and return normalized dict.

    Returns dict mapping quarter labels (e.g. 'Q3 2025') to metric dicts.
    """
    t = yf.Ticker(ticker.upper())

    financials = t.quarterly_financials
    balance = t.quarterly_balance_sheet
    cashflow = t.quarterly_cashflow

    if financials is None or financials.empty:
        return {}

    result: dict[str, dict[str, float | None]] = {}

    for col in financials.columns:
        q_label = normalize_quarter_label(col.date())
        metrics: dict[str, float | None] = {}

        # Income statement
        metrics["revenue_m"] = _to_millions(_safe_get(financials, "Total Revenue", col))

        gross = _safe_get(financials, "Gross Profit", col)
        if gross is None:
            # Insurance companies: compute from Revenue - Loss Adjustment Expense
            rev = _safe_get(financials, "Total Revenue", col)
            lae = _safe_get(financials, "Loss Adjustment Expense", col)
            if rev is not None and lae is not None:
                gross = rev - lae
        metrics["gross_profit_m"] = _to_millions(gross)

        op_inc = _safe_get(financials, "Operating Income", col)
        if op_inc is None:
            op_inc = _safe_get(financials, "EBIT", col)
        metrics["operating_income_m"] = _to_millions(op_inc)

        metrics["net_income_m"] = _to_millions(_safe_get(financials, "Net Income", col))
        metrics["eps"] = _safe_get(financials, "Basic EPS", col)

        # Balance sheet (columns may not align exactly, find nearest)
        if balance is not None and not balance.empty:
            bcol = _nearest_col(balance, col)
            if bcol is not None:
                equity_raw = _safe_get(balance, "Common Stock Equity", bcol)
                if equity_raw is None:
                    equity_raw = _safe_get(balance, "Total Equity Gross Minority Interest", bcol)
                metrics["total_equity_m"] = _to_millions(equity_raw)
                metrics["total_assets_m"] = _to_millions(
                    _safe_get(balance, "Total Assets", bcol)
                )
                metrics["cash_and_equivalents_m"] = _to_millions(
                    _safe_get(balance, "Cash And Cash Equivalents", bcol)
                )
                shares = _safe_get(balance, "Ordinary Shares Number", bcol)
                metrics["shares_outstanding_m"] = round(shares / 1_000_000, 2) if shares is not None else None

        # Cash flow
        if cashflow is not None and not cashflow.empty:
            ccol = _nearest_col(cashflow, col)
            if ccol is not None:
                metrics["free_cash_flow_m"] = _to_millions(
                    _safe_get(cashflow, "Free Cash Flow", ccol)
                )
                metrics["operating_cash_flow_m"] = _to_millions(
                    _safe_get(cashflow, "Operating Cash Flow", ccol)
                )
                metrics["capital_expenditure_m"] = _to_millions(
                    _safe_get(cashflow, "Capital Expenditure", ccol)
                )

        # Derived metrics
        equity = metrics.get("total_equity_m")
        shares_m = metrics.get("shares_outstanding_m")
        if equity is not None and shares_m is not None and shares_m > 0:
            metrics["bvps"] = round(equity / shares_m, 2)

        result[q_label] = metrics

    return result


def _nearest_col(df, target_col):
    """Find the column in df closest to target_col by date."""
    if target_col in df.columns:
        return target_col
    # Find nearest date
    target_ts = target_col.timestamp() if hasattr(target_col, "timestamp") else 0
    best = None
    best_diff = float("inf")
    for c in df.columns:
        diff = abs(c.timestamp() - target_ts)
        if diff < best_diff:
            best_diff = diff
            best = c
    # Only match within 45 days
    return best if best_diff < 45 * 86400 else None
