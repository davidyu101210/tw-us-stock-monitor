import math, numpy as np, pandas as pd

def sf(v):
    try:
        x=float(v); return None if math.isnan(x) or math.isinf(x) else x
    except Exception: return None

def rsi(s,p=14):
    if s is None or len(s)<p+2: return None
    d=s.diff(); g=d.clip(lower=0); l=-d.clip(upper=0)
    ag=g.ewm(alpha=1/p,adjust=False).mean(); al=l.ewm(alpha=1/p,adjust=False).mean()
    return sf((100-(100/(1+(ag/al.replace(0,np.nan))))).iloc[-1])

def atr(df,p=14):
    if df is None or df.empty or len(df)<p+2: return None
    h=pd.to_numeric(df["High"],errors="coerce"); l=pd.to_numeric(df["Low"],errors="coerce"); c=pd.to_numeric(df["Close"],errors="coerce"); pc=c.shift(1)
    tr=pd.concat([h-l,(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1)
    return sf(tr.rolling(p).mean().iloc[-1])

def snap(df):
    if df is None or df.empty: return {}
    c=pd.to_numeric(df["Close"],errors="coerce").dropna(); v=pd.to_numeric(df["Volume"],errors="coerce").fillna(0)
    return {"price":sf(c.iloc[-1]),"ma20":sf(c.rolling(20).mean().iloc[-1]) if len(c)>=20 else None,"ma60":sf(c.rolling(60).mean().iloc[-1]) if len(c)>=60 else None,
            "ma120":sf(c.rolling(120).mean().iloc[-1]) if len(c)>=120 else None,"rsi14":rsi(c),"atr14":atr(df),
            "high20":sf(pd.to_numeric(df["High"],errors="coerce").tail(20).max()) if len(df)>=20 else None,"low20":sf(pd.to_numeric(df["Low"],errors="coerce").tail(20).min()) if len(df)>=20 else None,
            "vol_ratio":sf(v.iloc[-1]/v.tail(20).mean()) if len(v)>=20 and v.tail(20).mean()>0 else None}

def build_score(df,info,inst_score=None,est_cost=None,positive_count=None,negative_count=None):
    s=snap(df); reasons=[]; risks=[]; t=i=f=v=m=0; risk=10
    p,ma20,ma60,ma120=s.get("price"),s.get("ma20"),s.get("ma60"),s.get("ma120"); r=s.get("rsi14"); vr=s.get("vol_ratio")
    if p and ma20:
        if p>=ma20: t+=7; reasons.append("股價站上 MA20")
        else: risks.append("股價仍在 MA20 下方")
    if ma20 and ma60:
        if ma20>=ma60: t+=7; reasons.append("MA20 ≥ MA60")
        else: risks.append("MA20 < MA60")
    if ma60 and ma120 and ma60>=ma120: t+=6; reasons.append("MA60 ≥ MA120")
    if r is not None:
        if 50<=r<=70: t+=5; reasons.append(f"RSI {r:.1f} 動能健康")
        elif r>75: risks.append(f"RSI {r:.1f} 偏熱")
    t=min(t,25)
    if inst_score is not None: i += round(max(0,min(inst_score,100))/100*14)
    if p and est_cost:
        d=(p-est_cost)/est_cost*100
        if -3<=d<=5: i+=4; reasons.append(f"接近法人推估成本（{d:+.1f}%）")
        elif d>12: risks.append(f"高於法人推估成本約 {d:.1f}%")
    if positive_count is not None and negative_count is not None:
        if positive_count>negative_count: i+=2; reasons.append("加碼數多於減碼數")
        elif negative_count>positive_count: risks.append("減碼數多於加碼數")
    i=min(i,20)
    rg,eg,gm,roe,fcf=info.get("revenue_growth"),info.get("earnings_growth"),info.get("gross_margin"),info.get("roe"),info.get("free_cashflow")
    if rg is not None:
        if rg>=0.15: f+=5; reasons.append(f"營收成長 {rg*100:.1f}%")
        elif rg>0: f+=2
        else: risks.append("營收成長為負")
    if eg is not None:
        if eg>=0.15: f+=5; reasons.append(f"獲利成長 {eg*100:.1f}%")
        elif eg>0: f+=2
        else: risks.append("獲利成長為負")
    if gm is not None and gm>=0.35: f+=3
    if roe is not None and roe>=0.20: f+=4
    if fcf is not None and fcf>0: f+=3
    f=min(f,20)
    pe,fpe,pb,peg,dy=info.get("trailing_pe"),info.get("forward_pe"),info.get("price_to_book"),info.get("peg"),info.get("dividend_yield")
    if pe is not None:
        if 0<pe<=18: v+=5
        elif pe<=30: v+=3
        elif pe>50: risks.append(f"P/E {pe:.1f} 偏高")
    if pe and fpe and fpe<pe: v+=3
    if peg is not None:
        if 0<peg<=1.5: v+=3
        elif peg>2.5: risks.append(f"PEG {peg:.2f} 偏高")
    if pb is not None and 0<pb<=3: v+=2
    if dy is not None:
        yy=dy*100 if dy<=1 else dy
        if yy>=2: v+=2
    v=min(v,15)
    if vr is not None:
        if vr>=1.5: m+=5
        elif vr>=1.0: m+=3
    if r is not None and 50<=r<=75: m+=3
    if p and s.get("high20") and p>=s["high20"]: m+=2
    m=min(m,10)
    if p and ma20 and (p-ma20)/ma20*100>12: risk-=3
    if p and s.get("atr14") and s["atr14"]/p*100>=6: risk-=3
    risk=max(0,min(risk,10))
    total=int(t+i+f+v+m+risk)
    label="條件偏強" if total>=80 else "偏多觀察" if total>=65 else "中性偏多" if total>=50 else "等待更佳條件" if total>=35 else "風險偏高"
    return {"score":total,"label":label,"technical":t,"institutional":i,"fundamentals":f,"valuation":v,"momentum":m,"risk":risk,"snapshot":s,"reasons":reasons[:8],"risks":risks[:8]}
