import pandas as pd

def consecutive_buy_days(values: pd.Series) -> int:
    count = 0
    for v in reversed(list(values.fillna(0))):
        try:
            if float(v) > 0:
                count += 1
            else:
                break
        except Exception:
            break
    return count

def institutional_score(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {
            "score": 0,
            "label": "無資料",
            "foreign_days": 0,
            "trust_days": 0,
            "dealer_days": 0,
        }

    fdays = consecutive_buy_days(df["foreign_net"])
    tdays = consecutive_buy_days(df["trust_net"])
    ddays = consecutive_buy_days(df["dealer_net"])

    last = df.iloc[-1]
    foreign = int(last["foreign_net"])
    trust = int(last["trust_net"])
    dealer = int(last["dealer_net"])
    total = int(last["total_net"])

    score = 0
    if total > 0: score += 20
    if foreign > 0: score += 15
    if trust > 0: score += 15
    if fdays >= 3: score += 15
    if fdays >= 5: score += 10
    if tdays >= 3: score += 15
    if tdays >= 5: score += 10
    if foreign > 0 and trust > 0: score += 10

    score = min(score, 100)

    if score >= 80:
        label = "高關注法人偏多"
    elif score >= 60:
        label = "法人偏多"
    elif score >= 40:
        label = "法人關注"
    else:
        label = "中性 / 偏弱"

    return {
        "score": score,
        "label": label,
        "foreign_days": fdays,
        "trust_days": tdays,
        "dealer_days": ddays,
        "foreign": foreign,
        "trust": trust,
        "dealer": dealer,
        "total": total,
    }
