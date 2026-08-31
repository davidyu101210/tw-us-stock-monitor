from datetime import datetime, time
from zoneinfo import ZoneInfo
import pandas as pd

def taiwan_market_status():
    now = datetime.now(ZoneInfo("Asia/Taipei"))
    if now.weekday() >= 5:
        return "休市", "週末"
    t = now.time()
    if time(8,30) <= t < time(9,0):
        return "盤前", "委託準備"
    if time(9,0) <= t <= time(13,30):
        return "盤中", "一般交易"
    if time(14,0) <= t <= time(14,30):
        return "盤後", "盤後定價"
    return "休市", "非一般交易時段"

def us_market_status():
    now = datetime.now(ZoneInfo("America/New_York"))
    if now.weekday() >= 5:
        return "休市", "週末"
    t = now.time()
    if time(4,0) <= t < time(9,30):
        return "盤前", "Pre-market"
    if time(9,30) <= t < time(16,0):
        return "盤中", "Regular"
    if time(16,0) <= t < time(20,0):
        return "盤後", "After-hours"
    return "休市", "Closed"

def estimate_tw_institutional_cost(inst_df, daily_df):
    if inst_df is None or inst_df.empty or daily_df is None or daily_df.empty:
        return None
    px = daily_df.reset_index().copy()
    px["date_key"] = pd.to_datetime(px.iloc[:,0], errors="coerce").dt.date
    inst = inst_df.copy()
    inst["date_key"] = pd.to_datetime(inst["date"], errors="coerce").dt.date
    m = inst.merge(px[["date_key","High","Low","Close"]], on="date_key", how="inner")
    if m.empty:
        return None
    m["tp"] = (pd.to_numeric(m["High"],errors="coerce")+pd.to_numeric(m["Low"],errors="coerce")+pd.to_numeric(m["Close"],errors="coerce"))/3
    m["w"] = pd.to_numeric(m["total_net"], errors="coerce").clip(lower=0)
    m = m[(m["w"]>0) & m["tp"].notna()]
    if m.empty or m["w"].sum() <= 0:
        return None
    return float((m["tp"]*m["w"]).sum()/m["w"].sum())

def tw_concentration(inst_df):
    if inst_df is None or inst_df.empty:
        return {"score":0,"label":"無資料","buy_days":0,"sell_days":0}
    total = pd.to_numeric(inst_df["total_net"],errors="coerce").fillna(0)
    foreign = pd.to_numeric(inst_df["foreign_net"],errors="coerce").fillna(0)
    trust = pd.to_numeric(inst_df["trust_net"],errors="coerce").fillna(0)
    buy_days, sell_days = int((total>0).sum()), int((total<0).sum())
    score = 0
    if buy_days>=3: score+=20
    if buy_days>=5: score+=15
    if buy_days>=8: score+=10
    if len(total.tail(3))==3 and (total.tail(3)>0).all(): score+=20
    if len(total.tail(5))==5 and (total.tail(5)>0).all(): score+=15
    if float(total.iloc[-1])>0: score+=10
    if float(foreign.iloc[-1])>0 and float(trust.iloc[-1])>0: score+=10
    score=min(score,100)
    label = "法人集中明顯加碼" if score>=80 else "法人偏多" if score>=60 else "法人溫和加碼" if score>=40 else "法人中性" if score>=20 else "法人偏弱"
    return {"score":score,"label":label,"buy_days":buy_days,"sell_days":sell_days}

def format_tw_history(inst_df):
    if inst_df is None or inst_df.empty:
        return pd.DataFrame()
    out = pd.DataFrame()
    out["日期"] = pd.to_datetime(inst_df["date"],errors="coerce").dt.date.astype(str)
    for src,dst in [("foreign_net","外資"),("trust_net","投信"),("dealer_net","自營商"),("total_net","三大法人合計")]:
        out[dst] = inst_df[src].map(lambda x: f"{int(x):,}")
    raw = pd.to_numeric(inst_df["total_net"],errors="coerce").fillna(0)
    out["判定"] = raw.map(lambda x:"🟢 加碼" if x>0 else ("🔴 減碼" if x<0 else "⚪ 持平"))
    return out
