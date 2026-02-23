from unittest.mock import patch, MagicMock
import pandas as pd

from eca.parsers.yfinance_fetcher import fetch_quarterly_metrics, normalize_quarter_label


def _make_df(data: dict, dates: list[str]) -> pd.DataFrame:
    """Helper to build a DataFrame matching yfinance's format."""
    cols = pd.to_datetime(dates)
    return pd.DataFrame(data, index=cols).T


def test_normalize_quarter_label():
    assert normalize_quarter_label("2025-09-30") == "Q3 2025"
    assert normalize_quarter_label("2025-03-31") == "Q1 2025"
    assert normalize_quarter_label("2024-12-31") == "Q4 2024"
    assert normalize_quarter_label("2025-06-30") == "Q2 2025"


def test_fetch_maps_revenue():
    financials = _make_df(
        {"Total Revenue": [387.8e6, 348.6e6]},
        ["2025-09-30", "2025-06-30"],
    )
    balance = _make_df(
        {"Common Stock Equity": [265e6, 235e6]},
        ["2025-09-30", "2025-06-30"],
    )
    cashflow = _make_df(
        {"Free Cash Flow": [53.7e6, 25.3e6]},
        ["2025-09-30", "2025-06-30"],
    )

    with patch("eca.parsers.yfinance_fetcher.yf") as mock_yf:
        mock_ticker = MagicMock()
        mock_ticker.quarterly_financials = financials
        mock_ticker.quarterly_balance_sheet = balance
        mock_ticker.quarterly_cashflow = cashflow
        mock_ticker.info = {"sharesOutstanding": 15_500_000}
        mock_yf.Ticker.return_value = mock_ticker

        result = fetch_quarterly_metrics("ROOT")

    assert "Q3 2025" in result
    assert abs(result["Q3 2025"]["revenue_m"] - 387.8) < 0.1
    assert abs(result["Q2 2025"]["revenue_m"] - 348.6) < 0.1


def test_fetch_computes_gross_profit_for_insurance():
    """Insurance companies lack Gross Profit; compute from Revenue - Loss Adjustment Expense."""
    financials = _make_df(
        {
            "Total Revenue": [387.8e6],
            "Loss Adjustment Expense": [306.4e6],
        },
        ["2025-09-30"],
    )
    balance = _make_df({"Common Stock Equity": [265e6]}, ["2025-09-30"])
    cashflow = _make_df({"Free Cash Flow": [53.7e6]}, ["2025-09-30"])

    with patch("eca.parsers.yfinance_fetcher.yf") as mock_yf:
        mock_ticker = MagicMock()
        mock_ticker.quarterly_financials = financials
        mock_ticker.quarterly_balance_sheet = balance
        mock_ticker.quarterly_cashflow = cashflow
        mock_ticker.info = {}
        mock_yf.Ticker.return_value = mock_ticker

        result = fetch_quarterly_metrics("ROOT")

    assert abs(result["Q3 2025"]["gross_profit_m"] - 81.4) < 0.1


def test_fetch_maps_balance_sheet_fields():
    financials = _make_df({"Total Revenue": [100e6]}, ["2025-09-30"])
    balance = _make_df(
        {
            "Common Stock Equity": [265e6],
            "Total Assets": [1500e6],
            "Cash And Cash Equivalents": [654e6],
            "Ordinary Shares Number": [15_528_458],
        },
        ["2025-09-30"],
    )
    cashflow = _make_df({}, ["2025-09-30"])

    with patch("eca.parsers.yfinance_fetcher.yf") as mock_yf:
        mock_ticker = MagicMock()
        mock_ticker.quarterly_financials = financials
        mock_ticker.quarterly_balance_sheet = balance
        mock_ticker.quarterly_cashflow = cashflow
        mock_ticker.info = {}
        mock_yf.Ticker.return_value = mock_ticker

        result = fetch_quarterly_metrics("ROOT")

    q = result["Q3 2025"]
    assert abs(q["total_equity_m"] - 265.0) < 0.1
    assert abs(q["cash_and_equivalents_m"] - 654.0) < 0.1
    assert abs(q["shares_outstanding_m"] - 15.53) < 0.1
