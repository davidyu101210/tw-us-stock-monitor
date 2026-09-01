from dataclasses import dataclass
from typing import Optional
import math
import pandas as pd
import numpy as np


@dataclass
class ScoreBreakdown:
    technical: int
    institutional: int
    fundamentals: int
    valuation: int
    momentum: int
    risk: int

    @property
    def total(self):
        return int(
            self.technical
            + self.institutional
            + self.fundamentals
            + self.valuation
            + self.momentum
            + self.risk
        )


def _safe_float(v):
    try:
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    except Exception:
        return None


def rsi(series: pd.Series, period=14):
    if series is None or len(series) < period + 2:
        return None
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return _safe_float(out.iloc[-1])


def atr(df: pd.DataFrame, period=14):
    if df is None or df.empty or len(df) < period + 2:
        return None
    high = pd.to_numeric(df["High"], errors="coerce")
    low = pd.to_numeric(df["Low"], errors="coerce")
    close = pd.to_numeric(df["Close"], errors="coerce")
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return _safe_float(tr.rolling(period).mean().iloc[-1])


def technical_snapshot(df: pd.DataFrame):
    if df is None or df.empty:
        return {}

    close = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if close.empty:
        return {}

    price = _safe_float(close.iloc[-1])
    ma20 = _safe_float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else None
    ma60 = _safe_float(close.rolling(60).mean().iloc[-1]) if len(close) >= 60 else None
    ma120 = _safe_float(close.rolling(120).mean().iloc[-1]) if len(close) >= 120 else None
    rsi14 = rsi(close, 14)
    atr14 = atr(df, 14)

    high20 = _safe_float(pd.to_numeric(df["High"], errors="coerce").tail(20).max()) if len(df) >= 20 else None
    low20 = _safe_float(pd.to_numeric(df["Low"], errors="coerce").tail(20).min()) if len(df) >= 20 else None

    volume = pd.to_numeric(df["Volume"], errors="coerce").fillna(0)
    vol20 = _safe_float(volume.tail(20).mean()) if len(volume) >= 20 else None
    vol_ratio = None
    if vol20 and vol20 > 0:
        vol_ratio = _safe_float(volume.iloc[-1] / vol20)

    return {
        "price": price,
        "ma20": ma20,
        "ma60": ma60,
        "ma120": ma120,
        "rsi14": rsi14,
        "atr14": atr14,
        "high20": high20,
        "low20": low20,
        "vol_ratio": vol_ratio,
    }


def score_technical(snap: dict):
    score = 0
    reasons = []
    risks = []

    p = snap.get("price")
    ma20 = snap.get("ma20")
    ma60 = snap.get("ma60")
    ma120 = snap.get("ma120")
    rsi14 = snap.get("rsi14")
    high20 = snap.get("high20")
    vol_ratio = snap.get("vol_ratio")

    if p and ma20:
        if p >= ma20:
            score += 6
            reasons.append("股價站上 MA20")
        else:
            risks.append("股價仍在 MA20 下方")

    if ma20 and ma60:
        if ma20 >= ma60:
            score += 7
            reasons.append("MA20 ≥ MA60，中期趨勢偏多")
        else:
            risks.append("MA20 < MA60，中期趨勢尚未轉強")

    if ma60 and ma120:
        if ma60 >= ma120:
            score += 6
            reasons.append("MA60 ≥ MA120，長波段結構偏多")

    if rsi14 is not None:
        if 50 <= rsi14 <= 70:
            score += 4
            reasons.append(f"RSI {rsi14:.1f}，動能健康")
        elif 70 < rsi14 <= 80:
            score += 2
            risks.append(f"RSI {rsi14:.1f}，短線偏熱")
        elif rsi14 > 80:
            risks.append(f"RSI {rsi14:.1f}，短線過熱")
        elif rsi14 < 40:
            risks.append(f"RSI {rsi14:.1f}，動能偏弱")

    if p and high20 and high20 > 0:
        d = (p - high20) / high20 * 100
        if -2 <= d <= 1:
            score += 2
            reasons.append("接近 20 日高點，具突破條件")

    score = min(score, 25)
    return score, reasons, risks


def score_institutional(inst_score=None, est_cost=None, price=None, positive_count=None, negative_count=None):
    score = 0
    reasons = []
    risks = []

    if inst_score is not None:
        base = max(0, min(float(inst_score), 100))
        score += int(round(base / 100 * 14))
        if base >= 70:
            reasons.append(f"法人集中分數 {base:.0f}/100")
        elif base < 40:
            risks.append(f"法人集中分數僅 {base:.0f}/100")

    if est_cost and price and est_cost > 0:
        d = (price - est_cost) / est_cost * 100
        if -3 <= d <= 5:
            score += 4
            reasons.append(f"現價接近法人推估成本區（{d:+.1f}%）")
        elif d > 12:
            risks.append(f"現價高於法人推估成本約 {d:.1f}%")
        elif d < -8:
            risks.append(f"現價低於法人推估成本約 {abs(d):.1f}%")

    if positive_count is not None and negative_count is not None:
        if positive_count > negative_count:
            score += 2
            reasons.append("加碼機構數多於減碼機構數")
        elif negative_count > positive_count:
            risks.append("減碼機構數多於加碼機構數")

    return min(score, 20), reasons, risks


def score_fundamentals(metrics: dict):
    score = 0
    reasons = []
    risks = []

    rev_growth = _safe_float(metrics.get("revenue_growth"))
    earnings_growth = _safe_float(metrics.get("earnings_growth"))
    gross_margin = _safe_float(metrics.get("gross_margin"))
    operating_margin = _safe_float(metrics.get("operating_margin"))
    roe = _safe_float(metrics.get("roe"))
    debt_to_equity = _safe_float(metrics.get("debt_to_equity"))
    fcf = _safe_float(metrics.get("free_cashflow"))

    if rev_growth is not None:
        if rev_growth >= 0.15:
            score += 4
            reasons.append(f"營收成長 {rev_growth*100:.1f}%")
        elif rev_growth > 0:
            score += 2
        else:
            risks.append("營收年增率為負")

    if earnings_growth is not None:
        if earnings_growth >= 0.15:
            score += 4
            reasons.append(f"獲利成長 {earnings_growth*100:.1f}%")
        elif earnings_growth > 0:
            score += 2
        else:
            risks.append("獲利成長為負")

    if gross_margin is not None and gross_margin >= 0.35:
        score += 3
        reasons.append(f"毛利率 {gross_margin*100:.1f}%")

    if operating_margin is not None and operating_margin >= 0.15:
        score += 3

    if roe is not None:
        if roe >= 0.20:
            score += 3
            reasons.append(f"ROE {roe*100:.1f}%")
        elif roe < 0:
            risks.append("ROE 為負")

    if fcf is not None:
        if fcf > 0:
            score += 2
            reasons.append("自由現金流為正")
        else:
            risks.append("自由現金流為負")

    if debt_to_equity is not None:
        # yfinance may report D/E as percentage-like number (e.g. 150)
        if debt_to_equity <= 100:
            score += 1
        elif debt_to_equity >= 250:
            risks.append("負債比偏高")

    return min(score, 20), reasons, risks


def score_valuation(metrics: dict):
    score = 0
    reasons = []
    risks = []

    pe = _safe_float(metrics.get("trailing_pe"))
    forward_pe = _safe_float(metrics.get("forward_pe"))
    pb = _safe_float(metrics.get("price_to_book"))
    peg = _safe_float(metrics.get("peg"))
    yield_ = _safe_float(metrics.get("dividend_yield"))

    if pe is not None:
        if 0 < pe <= 18:
            score += 5
            reasons.append(f"P/E {pe:.1f}，估值相對保守")
        elif pe <= 30:
            score += 3
        elif pe > 50:
            risks.append(f"P/E {pe:.1f}，估值偏高")

    if forward_pe is not None and pe is not None and forward_pe < pe:
        score += 3
        reasons.append("Forward P/E 低於目前 P/E")

    if peg is not None:
        if 0 < peg <= 1.5:
            score += 3
            reasons.append(f"PEG {peg:.2f}")
        elif peg > 2.5:
            risks.append(f"PEG {peg:.2f} 偏高")

    if pb is not None:
        if 0 < pb <= 3:
            score += 2
        elif pb > 10:
            risks.append(f"P/B {pb:.1f} 偏高")

    if yield_ is not None and yield_ > 0:
        # yfinance may return fraction
        yy = yield_ * 100 if yield_ <= 1 else yield_
        if yy >= 2:
            score += 2
            reasons.append(f"股息殖利率約 {yy:.1f}%")

    return min(score, 15), reasons, risks


def score_momentum(snap: dict):
    score = 0
    reasons = []
    risks = []

    vr = snap.get("vol_ratio")
    rsi14 = snap.get("rsi14")
    p = snap.get("price")
    high20 = snap.get("high20")

    if vr is not None:
        if vr >= 1.5:
            score += 5
            reasons.append(f"成交量為 20 日均量 {vr:.1f} 倍")
        elif vr >= 1.0:
            score += 3

    if rsi14 is not None and 50 <= rsi14 <= 75:
        score += 3

    if p and high20 and high20 > 0:
        d = (p - high20) / high20 * 100
        if d >= 0:
            score += 2
            reasons.append("價格突破近 20 日高點")

    return min(score, 10), reasons, risks


def score_risk(snap: dict, event_days=None):
    score = 10
    reasons = []
    risks = []

    p = snap.get("price")
    ma20 = snap.get("ma20")
    atr14 = snap.get("atr14")

    if p and ma20 and ma20 > 0:
        d = (p - ma20) / ma20 * 100
        if d > 12:
            score -= 3
            risks.append(f"現價高於 MA20 約 {d:.1f}%，乖離偏大")
        elif -3 <= d <= 6:
            reasons.append("現價與 MA20 距離合理")

    if p and atr14 and p > 0:
        atr_pct = atr14 / p * 100
        if atr_pct >= 6:
            score -= 3
            risks.append(f"ATR 約 {atr_pct:.1f}%，波動偏高")
        elif atr_pct <= 3:
            reasons.append("ATR 波動相對可控")

    if event_days is not None:
        try:
            d = int(event_days)
            if 0 <= d <= 7:
                score -= 4
                risks.append(f"重大事件/財報約 {d} 天內，事件風險高")
            elif 8 <= d <= 14:
                score -= 2
                risks.append(f"重大事件/財報約 {d} 天內")
        except Exception:
            pass

    return max(0, min(score, 10)), reasons, risks


def build_decision(
    price_df: pd.DataFrame,
    fundamentals: dict,
    inst_score=None,
    est_cost=None,
    positive_count=None,
    negative_count=None,
    event_days=None,
):
    snap = technical_snapshot(price_df)

    t, r1, x1 = score_technical(snap)
    i, r2, x2 = score_institutional(
        inst_score=inst_score,
        est_cost=est_cost,
        price=snap.get("price"),
        positive_count=positive_count,
        negative_count=negative_count,
    )
    f, r3, x3 = score_fundamentals(fundamentals)
    v, r4, x4 = score_valuation(fundamentals)
    m, r5, x5 = score_momentum(snap)
    risk, r6, x6 = score_risk(snap, event_days=event_days)

    breakdown = ScoreBreakdown(
        technical=t,
        institutional=i,
        fundamentals=f,
        valuation=v,
        momentum=m,
        risk=risk,
    )

    reasons = r1 + r2 + r3 + r4 + r5 + r6
    risks = x1 + x2 + x3 + x4 + x5 + x6

    total = breakdown.total

    if total >= 80:
        label = "條件偏強"
    elif total >= 65:
        label = "偏多觀察"
    elif total >= 50:
        label = "中性偏多"
    elif total >= 35:
        label = "等待更佳條件"
    else:
        label = "風險偏高"

    return {
        "score": total,
        "label": label,
        "breakdown": breakdown,
        "snapshot": snap,
        "reasons": reasons[:8],
        "risks": risks[:8],
    }
