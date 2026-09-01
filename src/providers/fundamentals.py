import pandas as pd
import yfinance as yf


def _num(v):
    try:
        return float(v)
    except Exception:
        return None


def fetch_fundamentals(ticker: str) -> dict:
    """
    Public fundamentals through yfinance.
    Fields vary by ticker and availability.
    """
    out = {}
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        out = {
            "revenue_growth": _num(info.get("revenueGrowth")),
            "earnings_growth": _num(info.get("earningsGrowth")),
            "gross_margin": _num(info.get("grossMargins")),
            "operating_margin": _num(info.get("operatingMargins")),
            "roe": _num(info.get("returnOnEquity")),
            "debt_to_equity": _num(info.get("debtToEquity")),
            "free_cashflow": _num(info.get("freeCashflow")),
            "trailing_pe": _num(info.get("trailingPE")),
            "forward_pe": _num(info.get("forwardPE")),
            "price_to_book": _num(info.get("priceToBook")),
            "peg": _num(info.get("pegRatio")),
            "dividend_yield": _num(info.get("dividendYield")),
            "market_cap": _num(info.get("marketCap")),
            "beta": _num(info.get("beta")),
            "target_mean_price": _num(info.get("targetMeanPrice")),
            "recommendation_mean": _num(info.get("recommendationMean")),
            "recommendation_key": info.get("recommendationKey"),
            "earnings_timestamp": info.get("earningsTimestamp"),
        }
    except Exception:
        pass
    return out


def fetch_price_history(ticker: str, period="1y") -> pd.DataFrame:
    try:
        df = yf.Ticker(ticker).history(
            period=period,
            interval="1d",
            auto_adjust=False,
            prepost=False,
        )
        if df is None:
            return pd.DataFrame()
        return df.dropna(how="all")
    except Exception:
        return pd.DataFrame()
