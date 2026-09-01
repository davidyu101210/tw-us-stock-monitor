from datetime import date, timedelta
import pandas as pd
import requests

URL = "https://www.twse.com.tw/rwd/zh/fund/T86"

def _i(v):
    try: return int(str(v).replace(",","").strip())
    except Exception: return 0

def fetch_day(d):
    r = requests.get(URL, params={"date":d.strftime("%Y%m%d"),"selectType":"ALLBUT0999","response":"json"},
                     timeout=15, headers={"User-Agent":"Mozilla/5.0"})
    r.raise_for_status()
    payload = r.json()
    fields, data = payload.get("fields",[]), payload.get("data",[])
    if not fields or not data: return {}
    def idx(key, fallback=None):
        for i,f in enumerate(fields):
            if key in str(f): return i
        return fallback
    si, fi, ti, di = idx("證券代號",0), idx("外陸資買賣超股數",4), idx("投信買賣超股數",10), idx("自營商買賣超股數",11)
    toi = idx("三大法人買賣超股數", len(fields)-1)
    out = {}
    for row in data:
        try:
            code = str(row[si]).strip()
            out[code] = {"date":d,"foreign_net":_i(row[fi]),"trust_net":_i(row[ti]),"dealer_net":_i(row[di]),"total_net":_i(row[toi])}
        except Exception:
            pass
    return out

def fetch_recent(code, trading_days=10, lookback_days=35):
    rows, today = [], date.today()
    for n in range(lookback_days):
        d = today - timedelta(days=n)
        if d.weekday() >= 5: continue
        try:
            day = fetch_day(d)
            if code in day:
                rows.append(day[code])
                if len(rows) >= trading_days: break
        except Exception:
            continue
    return pd.DataFrame() if not rows else pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
