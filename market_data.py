import pandas as pd
import yfinance as yf

def fetch_history(symbol, period="1y", interval="1d", prepost=False):
    try:
        df = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False, prepost=prepost)
        return pd.DataFrame() if df is None else df.dropna(how="all")
    except Exception:
        return pd.DataFrame()

def fetch_info(symbol):
    try:
        info = yf.Ticker(symbol).info or {}
    except Exception:
        info = {}
    def num(key):
        try:
            v = info.get(key)
            return None if v is None else float(v)
        except Exception:
            return None
    return {
        "name": info.get("longName") or info.get("shortName") or symbol,
        "revenue_growth": num("revenueGrowth"),
        "earnings_growth": num("earningsGrowth"),
        "gross_margin": num("grossMargins"),
        "roe": num("returnOnEquity"),
        "free_cashflow": num("freeCashflow"),
        "trailing_pe": num("trailingPE"),
        "forward_pe": num("forwardPE"),
        "price_to_book": num("priceToBook"),
        "peg": num("pegRatio"),
        "dividend_yield": num("dividendYield"),
    }
