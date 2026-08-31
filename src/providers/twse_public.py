from datetime import date, timedelta
import requests
import pandas as pd

BASE = "https://www.twse.com.tw/rwd/zh/fund/T86"

def _i(v):
    try:
        return int(str(v).replace(",", "").strip())
    except Exception:
        return 0

def fetch_day(d: date):
    params = {
        "date": d.strftime("%Y%m%d"),
        "selectType": "ALLBUT0999",
        "response": "json",
    }
    r = requests.get(
        BASE,
        params=params,
        timeout=15,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    r.raise_for_status()
    payload = r.json()
    fields = payload.get("fields", [])
    data = payload.get("data", [])

    if not fields or not data:
        return {}

    def idx(needle, fallback=None):
        for n, f in enumerate(fields):
            if needle in str(f):
                return n
        return fallback

    si = idx("證券代號", 0)
    fi = idx("外陸資買賣超股數", 4)
    ti = idx("投信買賣超股數", 10)
    di = idx("自營商買賣超股數", 11)
    total_i = idx("三大法人買賣超股數", len(fields)-1)

    result = {}
    for row in data:
        try:
            code = str(row[si]).strip()
            result[code] = {
                "date": d,
                "foreign_net": _i(row[fi]),
                "trust_net": _i(row[ti]),
                "dealer_net": _i(row[di]),
                "total_net": _i(row[total_i]),
            }
        except Exception:
            continue
    return result

def fetch_recent(symbol_code: str, trading_days=10, lookback_calendar_days=30) -> pd.DataFrame:
    rows = []
    today = date.today()

    for n in range(lookback_calendar_days):
        d = today - timedelta(days=n)
        if d.weekday() >= 5:
            continue
        try:
            day = fetch_day(d)
            if symbol_code in day:
                rows.append(day[symbol_code])
                if len(rows) >= trading_days:
                    break
        except Exception:
            continue

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
