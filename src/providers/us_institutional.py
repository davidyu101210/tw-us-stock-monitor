import math
import pandas as pd
import yfinance as yf


def _safe_df(obj):
    try:
        if obj is None:
            return pd.DataFrame()
        if isinstance(obj, pd.DataFrame):
            return obj.copy()
        return pd.DataFrame(obj)
    except Exception:
        return pd.DataFrame()


def fetch_institutional_holders(ticker: str) -> pd.DataFrame:
    """
    Uses public Yahoo Finance data via yfinance.
    Typical columns may include:
      Holder, Shares, Date Reported, % Out, Value
    Availability varies by symbol / region.
    """
    try:
        t = yf.Ticker(ticker)
        df = _safe_df(t.institutional_holders)
        return df
    except Exception:
        return pd.DataFrame()


def quarter_vwap(ticker: str, period="3mo"):
    """
    Approximate VWAP using daily typical price * daily volume.
    This is a market-price estimate, not an institution's actual execution cost.
    """
    try:
        hist = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=False)
        if hist is None or hist.empty:
            return None
        typical = (hist["High"] + hist["Low"] + hist["Close"]) / 3.0
        vol = hist["Volume"].fillna(0).astype(float)
        if vol.sum() <= 0:
            return float(hist["Close"].mean())
        return float((typical * vol).sum() / vol.sum())
    except Exception:
        return None


def institutional_reference(ticker: str) -> dict:
    """
    Produces a conservative 'institutional estimated cost reference'.

    IMPORTANT:
    - 13F does NOT disclose actual purchase price.
    - Holder 'Value / Shares' is effectively an implied reporting-date value per share.
    - We combine latest disclosed holder-implied price with trailing-quarter VWAP
      only as a reference estimate, never as a true cost basis.
    """
    holders = fetch_institutional_holders(ticker)
    qvwap = quarter_vwap(ticker)

    result = {
        "holders": holders,
        "quarter_vwap": qvwap,
        "implied_report_price": None,
        "estimated_cost": qvwap,
        "confidence": "低",
        "latest_report_date": None,
    }

    if holders.empty:
        return result

    # Normalize column names flexibly
    cols = {str(c).lower(): c for c in holders.columns}
    shares_col = next((c for k, c in cols.items() if "share" in k), None)
    value_col = next((c for k, c in cols.items() if "value" in k), None)
    date_col = next((c for k, c in cols.items() if "date" in k), None)

    if date_col is not None:
        try:
            dates = pd.to_datetime(holders[date_col], errors="coerce")
            if dates.notna().any():
                result["latest_report_date"] = dates.max().date().isoformat()
        except Exception:
            pass

    implied = None
    if shares_col is not None and value_col is not None:
        try:
            s = pd.to_numeric(holders[shares_col], errors="coerce").fillna(0)
            v = pd.to_numeric(holders[value_col], errors="coerce").fillna(0)
            mask = (s > 0) & (v > 0)
            if mask.any() and s[mask].sum() > 0:
                implied = float(v[mask].sum() / s[mask].sum())
        except Exception:
            implied = None

    result["implied_report_price"] = implied

    if qvwap is not None and implied is not None:
        # Reference estimate only: midpoint of quarter VWAP and report-date implied value.
        result["estimated_cost"] = float((qvwap + implied) / 2.0)
        spread = abs(qvwap - implied) / max(result["estimated_cost"], 1e-9)
        result["confidence"] = "中" if spread <= 0.08 else "低"
    elif qvwap is not None:
        result["estimated_cost"] = qvwap
        result["confidence"] = "低"
    elif implied is not None:
        result["estimated_cost"] = implied
        result["confidence"] = "低"

    return result


def classify_change(pct_change):
    try:
        x = float(pct_change)
    except Exception:
        return "⚪ 無法判定"

    if x >= 0.05:
        return "🟢 明顯加碼"
    if x >= 0.01:
        return "🟢 加碼"
    if x > 0:
        return "🟡 小幅加碼"
    if x <= -0.05:
        return "🔴 明顯減碼"
    if x <= -0.01:
        return "🔴 減碼"
    if x < 0:
        return "🟠 小幅減碼"
    return "⚪ 持平"


def concentration_score(holders: pd.DataFrame) -> dict:
    """
    Scores breadth and intensity of institutional accumulation.
    This is a heuristic, not an investment recommendation.
    """
    if holders is None or holders.empty:
        return {"score": 0, "label": "無資料", "positive": 0, "negative": 0}

    cols = {str(c).lower(): c for c in holders.columns}
    ch_col = next((c for k, c in cols.items() if "pctchange" in k or "pct change" in k), None)
    held_col = next((c for k, c in cols.items() if "pctheld" in k or "pct held" in k), None)

    if ch_col is None:
        return {"score": 0, "label": "缺少變化資料", "positive": 0, "negative": 0}

    ch = pd.to_numeric(holders[ch_col], errors="coerce").fillna(0)
    positive = int((ch > 0).sum())
    negative = int((ch < 0).sum())

    score = 0
    # breadth
    if positive >= 3: score += 20
    if positive >= 5: score += 15
    if positive >= 8: score += 10
    if negative == 0 and positive > 0: score += 10

    # intensity
    strong_add = int((ch >= 0.05).sum())
    add = int((ch >= 0.01).sum())
    score += min(strong_add * 10, 30)
    score += min(add * 3, 15)

    # weighting by ownership
    if held_col is not None:
        held = pd.to_numeric(holders[held_col], errors="coerce").fillna(0)
        weighted = float((held * ch).sum())
        if weighted > 0.005:
            score += 10
        elif weighted > 0:
            score += 5

    score = min(score, 100)

    if score >= 80:
        label = "法人集中明顯加碼"
    elif score >= 60:
        label = "法人偏多"
    elif score >= 40:
        label = "法人溫和加碼"
    elif score >= 20:
        label = "法人中性"
    else:
        label = "法人偏弱"

    return {
        "score": score,
        "label": label,
        "positive": positive,
        "negative": negative,
    }


def format_holders_chinese(holders: pd.DataFrame) -> pd.DataFrame:
    if holders is None or holders.empty:
        return pd.DataFrame()

    df = holders.copy()
    rename = {
        "Date Reported": "申報日期",
        "Holder": "機構",
        "pctHeld": "持股比例",
        "Shares": "持股數",
        "Value": "持股市值",
        "pctChange": "本季增減",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    if "持股比例" in df.columns:
        df["持股比例"] = pd.to_numeric(df["持股比例"], errors="coerce").map(
            lambda x: "" if pd.isna(x) else f"{x*100:.2f}%"
        )

    if "持股數" in df.columns:
        def fmt_shares(x):
            try:
                x = float(x)
                if x >= 1e8:
                    return f"{x/1e8:.2f} 億股"
                if x >= 1e4:
                    return f"{x/1e4:.1f} 萬股"
                return f"{int(x):,} 股"
            except Exception:
                return ""
        df["持股數"] = df["持股數"].map(fmt_shares)

    if "持股市值" in df.columns:
        def fmt_value(x):
            try:
                x = float(x)
                if x >= 1e9:
                    return f"${x/1e9:.2f}B"
                if x >= 1e6:
                    return f"${x/1e6:.2f}M"
                return f"${x:,.0f}"
            except Exception:
                return ""
        df["持股市值"] = df["持股市值"].map(fmt_value)

    if "本季增減" in df.columns:
        raw = pd.to_numeric(df["本季增減"], errors="coerce")
        df["判定"] = raw.map(classify_change)
        df["本季增減"] = raw.map(lambda x: "" if pd.isna(x) else f"{x*100:+.2f}%")

    if "申報日期" in df.columns:
        try:
            df["申報日期"] = pd.to_datetime(df["申報日期"], errors="coerce").dt.date.astype(str)
        except Exception:
            pass

    wanted = ["機構", "持股比例", "持股數", "持股市值", "本季增減", "判定", "申報日期"]
    return df[[c for c in wanted if c in df.columns]]
