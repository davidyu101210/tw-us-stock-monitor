from pathlib import Path
from datetime import datetime, timezone
import json, pandas as pd, yfinance as yf

CACHE = Path(__file__).resolve().parents[2] / "cache"
CACHE.mkdir(exist_ok=True)

def _path(symbol): return CACHE / f"13f_{symbol.upper()}.json"

def fetch_holders(symbol):
    try:
        df = yf.Ticker(symbol).institutional_holders
        return pd.DataFrame() if df is None else df.copy()
    except Exception:
        return pd.DataFrame()

def quarter_vwap(symbol):
    try:
        h = yf.Ticker(symbol).history(period="3mo", interval="1d", auto_adjust=False)
        if h is None or h.empty: return None
        tp = (h["High"]+h["Low"]+h["Close"])/3
        v = h["Volume"].fillna(0).astype(float)
        return float((tp*v).sum()/v.sum()) if v.sum()>0 else float(h["Close"].mean())
    except Exception:
        return None

def build(symbol):
    holders, qv = fetch_holders(symbol), quarter_vwap(symbol)
    implied, report = None, None
    if not holders.empty:
        cols = {str(c).lower():c for c in holders.columns}
        sc = next((c for k,c in cols.items() if "share" in k), None)
        vc = next((c for k,c in cols.items() if "value" in k), None)
        dc = next((c for k,c in cols.items() if "date" in k), None)
        if dc is not None:
            dates = pd.to_datetime(holders[dc], errors="coerce")
            if dates.notna().any(): report = dates.max().date().isoformat()
        if sc is not None and vc is not None:
            s = pd.to_numeric(holders[sc], errors="coerce").fillna(0)
            v = pd.to_numeric(holders[vc], errors="coerce").fillna(0)
            m = (s>0)&(v>0)
            if m.any() and s[m].sum()>0: implied = float(v[m].sum()/s[m].sum())
    est = (qv+implied)/2 if qv is not None and implied is not None else (qv if qv is not None else implied)
    return {"holders":holders,"quarter_vwap":qv,"implied_report_price":implied,"estimated_cost":est,"latest_report_date":report}

def _ser(df):
    if df is None or df.empty: return []
    x = df.copy()
    for c in x.columns:
        if pd.api.types.is_datetime64_any_dtype(x[c]): x[c] = x[c].astype(str)
    x = x.astype(object).where(pd.notna(x), None)
    return x.to_dict("records")

def save(symbol, data):
    payload = dict(data)
    payload["holders"] = _ser(data.get("holders"))
    payload["saved_at"] = datetime.now(timezone.utc).isoformat()
    _path(symbol).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

def load(symbol):
    p = _path(symbol)
    if not p.exists(): return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        d["holders"] = pd.DataFrame(d.get("holders") or [])
        d["data_status"] = "沿用最後成功資料"
        d["is_fallback"] = True
        return d
    except Exception:
        return None

def get_reference(symbol):
    fresh = build(symbol)
    h = fresh.get("holders")
    ok = fresh.get("estimated_cost") is not None or fresh.get("latest_report_date") is not None or (h is not None and not h.empty)
    if ok:
        fresh["data_status"] = "最新可取得資料"; fresh["is_fallback"] = False
        try: save(symbol, fresh)
        except Exception: pass
        return fresh
    cached = load(symbol)
    if cached: return cached
    fresh["data_status"] = "目前無可用資料"; fresh["is_fallback"] = False
    return fresh

def concentration_score(holders):
    if holders is None or holders.empty: return {"score":0,"positive":0,"negative":0,"label":"無資料"}
    cols = {str(c).lower():c for c in holders.columns}
    cc = next((c for k,c in cols.items() if "pctchange" in k or "pct change" in k), None)
    if cc is None: return {"score":0,"positive":0,"negative":0,"label":"缺少變化資料"}
    ch = pd.to_numeric(holders[cc], errors="coerce").fillna(0)
    pos, neg = int((ch>0).sum()), int((ch<0).sum())
    score = min((20 if pos>=3 else 0)+(20 if pos>=5 else 0)+(20 if pos>=8 else 0)+min(int((ch>=0.01).sum())*4,20)+min(int((ch>=0.05).sum())*10,20),100)
    label = "法人集中明顯加碼" if score>=80 else "法人偏多" if score>=60 else "法人溫和加碼" if score>=40 else "法人中性" if score>=20 else "法人偏弱"
    return {"score":score,"positive":pos,"negative":neg,"label":label}

def format_holders(holders):
    if holders is None or holders.empty: return pd.DataFrame()
    df = holders.copy().rename(columns={"Date Reported":"申報日期","Holder":"機構","pctHeld":"持股比例","Shares":"持股數","Value":"持股市值","pctChange":"本季增減"})
    if "持股比例" in df: 
        x = pd.to_numeric(df["持股比例"], errors="coerce"); df["持股比例"] = x.map(lambda v:"" if pd.isna(v) else f"{v*100:.2f}%")
    if "本季增減" in df:
        x = pd.to_numeric(df["本季增減"], errors="coerce")
        df["判定"] = x.map(lambda v:"🟢 加碼" if pd.notna(v) and v>0 else ("🔴 減碼" if pd.notna(v) and v<0 else "⚪ 持平"))
        df["本季增減"] = x.map(lambda v:"" if pd.isna(v) else f"{v*100:+.2f}%")
    cols = ["機構","持股比例","持股數","持股市值","本季增減","判定","申報日期"]
    return df[[c for c in cols if c in df.columns]]
