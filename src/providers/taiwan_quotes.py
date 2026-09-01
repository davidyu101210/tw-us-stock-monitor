import pandas as pd
import yfinance as yf

def yahoo_symbol(code: str, market: str = "TWSE") -> str:
    if market == "TPEX":
        return f"{code}.TWO"
    return f"{code}.TW"

def fetch_history(code: str, market: str = "TWSE", period="5d", interval="5m") -> pd.DataFrame:
    symbol = yahoo_symbol(code, market)
    try:
        df = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False, prepost=False)
        if df is None:
            return pd.DataFrame()
        return df.dropna(how="all")
    except Exception:
        return pd.DataFrame()

def fetch_daily(code: str, market: str = "TWSE", period="3mo") -> pd.DataFrame:
    symbol = yahoo_symbol(code, market)
    try:
        df = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=False)
        if df is None:
            return pd.DataFrame()
        return df.dropna(how="all")
    except Exception:
        return pd.DataFrame()
