from datetime import datetime, time
from zoneinfo import ZoneInfo

def market_status(market):
    if market == "TW":
        now = datetime.now(ZoneInfo("Asia/Taipei"))
        if now.weekday() >= 5:
            return "休市", "週末"
        t = now.time()
        if time(8,30) <= t < time(9,0): return "盤前", "台股盤前"
        if time(9,0) <= t <= time(13,30): return "盤中", "一般交易"
        if time(14,0) <= t <= time(14,30): return "盤後", "盤後定價"
        return "休市", "非一般交易時段"
    now = datetime.now(ZoneInfo("America/New_York"))
    if now.weekday() >= 5:
        return "休市", "週末"
    t = now.time()
    if time(4,0) <= t < time(9,30): return "盤前", "Pre-market"
    if time(9,30) <= t < time(16,0): return "盤中", "Regular"
    if time(16,0) <= t < time(20,0): return "盤後", "After-hours"
    return "休市", "Closed"

def yahoo_symbol(market, code, tw_market="TWSE"):
    if market == "US":
        return code.upper()
    return f"{code}.TWO" if tw_market == "TPEX" else f"{code}.TW"
