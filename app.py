from datetime import datetime
import json
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.providers.twse_public import fetch_recent
from src.providers.taiwan_quotes import fetch_history, fetch_daily
from src.institutional import institutional_score
from src.decision_engine import build_decision
from src.providers.fundamentals import fetch_fundamentals, fetch_price_history
from src.tw_parity import taiwan_market_status, us_market_status, estimate_tw_institutional_cost, tw_concentration, format_tw_history
from src.providers.us_institutional import institutional_reference_with_fallback_with_fallback, concentration_score, format_holders_chinese

st.set_page_config(page_title="台美股看盤 iPhone v2.0", layout="wide")

# ---- Session state initialization ----
if "last_13f_check" not in st.session_state:
    st.session_state["last_13f_check"] = None
if "last_13f_report_date" not in st.session_state:
    st.session_state["last_13f_report_date"] = None
if "last_13f_status" not in st.session_state:
    st.session_state["last_13f_status"] = "尚未檢查"


@st.cache_data(ttl=1800)
def load_fundamentals_for_decision(ticker):
    return fetch_fundamentals(ticker)

@st.cache_data(ttl=900)
def load_daily_history_for_decision(ticker):
    return fetch_price_history(ticker, period="1y")

def render_decision_panel(title, decision, fundamentals, est_cost=None):
    st.subheader(title)

    b = decision["breakdown"]
    c1, c2, c3 = st.columns(3)
    c1.metric("綜合買入條件分數", f'{decision["score"]}/100')
    c2.metric("目前判定", decision["label"])
    snap = decision["snapshot"]
    stop_text = "無資料"
    if snap.get("price") and snap.get("atr14"):
        stop_text = f'{snap["price"] - 2*snap["atr14"]:.2f}'
    c3.metric("ATR 2 倍風險參考價", stop_text)

    st.progress(min(max(decision["score"], 0), 100) / 100)

    score_df = pd.DataFrame([{
        "技術趨勢": f"{b.technical}/25",
        "法人籌碼": f"{b.institutional}/20",
        "基本面": f"{b.fundamentals}/20",
        "估值": f"{b.valuation}/15",
        "動能": f"{b.momentum}/10",
        "風險控制": f"{b.risk}/10",
    }])
    st.dataframe(score_df, use_container_width=True, hide_index=True)

    left, right = st.columns(2)
    with left:
        st.markdown("#### ✅ 買入理由")
        if decision["reasons"]:
            for reason in decision["reasons"]:
                st.write("• " + reason)
        else:
            st.caption("目前沒有足夠的正向條件。")

    with right:
        st.markdown("#### ⚠️ 不買 / 等待理由")
        if decision["risks"]:
            for risk in decision["risks"]:
                st.write("• " + risk)
        else:
            st.caption("目前未偵測到明顯風險條件。")

    st.markdown("#### 關鍵位置")
    s = decision["snapshot"]
    pos = pd.DataFrame([{
        "現價": None if s.get("price") is None else round(s["price"], 2),
        "MA20": None if s.get("ma20") is None else round(s["ma20"], 2),
        "MA60": None if s.get("ma60") is None else round(s["ma60"], 2),
        "MA120": None if s.get("ma120") is None else round(s["ma120"], 2),
        "20日支撐": None if s.get("low20") is None else round(s["low20"], 2),
        "20日壓力": None if s.get("high20") is None else round(s["high20"], 2),
        "RSI14": None if s.get("rsi14") is None else round(s["rsi14"], 1),
        "法人推估成本": None if est_cost is None else round(est_cost, 2),
    }])
    st.dataframe(pos, use_container_width=True, hide_index=True)

    st.markdown("#### 基本面 / 估值摘要")
    def pct(v):
        try:
            return f"{float(v)*100:.1f}%"
        except Exception:
            return "無資料"

    fd = pd.DataFrame([{
        "營收成長": pct(fundamentals.get("revenue_growth")),
        "獲利成長": pct(fundamentals.get("earnings_growth")),
        "毛利率": pct(fundamentals.get("gross_margin")),
        "ROE": pct(fundamentals.get("roe")),
        "P/E": fundamentals.get("trailing_pe"),
        "Forward P/E": fundamentals.get("forward_pe"),
        "P/B": fundamentals.get("price_to_book"),
        "PEG": fundamentals.get("peg"),
    }])
    st.dataframe(fd, use_container_width=True, hide_index=True)

    st.caption(
        "此分數是資訊整理工具，不代表保證獲利或個人化投資建議。"
        "法人推估成本、估值與公開基本面資料都可能有延遲或缺漏。"
    )



# ----- iPhone / PWA mobile tuning -----
st.markdown("""
<style>
@media (max-width: 768px) {
    .block-container {
        padding-top: 0.8rem !important;
        padding-left: 0.7rem !important;
        padding-right: 0.7rem !important;
        padding-bottom: 4rem !important;
    }
    h1 { font-size: 1.55rem !important; }
    h2 { font-size: 1.25rem !important; }
    h3 { font-size: 1.1rem !important; }
    [data-testid="stMetricValue"] {
        font-size: 1.4rem !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.78rem !important;
    }
    [data-testid="stHorizontalBlock"] {
        gap: 0.45rem !important;
    }
    .stDataFrame {
        font-size: 0.78rem !important;
    }
    section[data-testid="stSidebar"] {
        width: 82vw !important;
        min-width: 82vw !important;
    }
}
</style>
""", unsafe_allow_html=True)

components.html("""
<script>
(function() {
  try {
    const d = window.parent.document;
    if (!d.querySelector('meta[name="apple-mobile-web-app-capable"]')) {
      const m1 = d.createElement('meta');
      m1.name = 'apple-mobile-web-app-capable';
      m1.content = 'yes';
      d.head.appendChild(m1);

      const m2 = d.createElement('meta');
      m2.name = 'apple-mobile-web-app-status-bar-style';
      m2.content = 'black-translucent';
      d.head.appendChild(m2);

      const m3 = d.createElement('meta');
      m3.name = 'theme-color';
      m3.content = '#0e1117';
      d.head.appendChild(m3);

      const vp = d.querySelector('meta[name="viewport"]');
      if (vp) {
        vp.setAttribute('content', 'width=device-width, initial-scale=1, viewport-fit=cover');
      }
    }
  } catch (e) {}
})();
</script>
""", height=0)

st_autorefresh(interval=60000, key="auto_refresh")

st.title("台股＋美股自動看盤 v2.0 買入決策版")
st.caption("台股：自製 K 線＋TWSE 法人；美股：TradingView Widget。")

TW_DEFAULTS = {
    "台積電 2330": ("TWSE", "2330"),
    "元大台灣50 0050": ("TWSE", "0050"),
}

US_DEFAULTS = {
    "Apple AAPL": "NASDAQ:AAPL",
    "NVIDIA NVDA": "NASDAQ:NVDA",
    "Microsoft MSFT": "NASDAQ:MSFT",
}

with st.sidebar:
    market_mode = st.radio("市場", ["台股", "美股"], index=0)

session_name, session_desc = taiwan_market_status() if market_mode == "台股" else us_market_status()
mc1, mc2 = st.columns(2)
mc1.metric("目前市場狀態", session_name)
mc2.metric("交易時段", session_desc)

if market_mode == "台股":
    with st.sidebar:
        quick = st.selectbox("快速選擇", list(TW_DEFAULTS.keys()))
        default_market, default_code = TW_DEFAULTS[quick]
        tw_market = st.selectbox("市場別", ["TWSE", "TPEX"], index=0 if default_market == "TWSE" else 1)
        code = st.text_input("股票代號", value=default_code).strip()
        interval_label = st.selectbox("K 線週期", ["5 分", "15 分", "30 分", "60 分", "日 K"], index=0)

    interval_map = {
        "5 分": ("5d", "5m"),
        "15 分": ("5d", "15m"),
        "30 分": ("5d", "30m"),
        "60 分": ("1mo", "60m"),
        "日 K": ("3mo", "1d"),
    }
    period, interval = interval_map[interval_label]

    @st.cache_data(ttl=45)
    def load_tw_chart(code, tw_market, period, interval):
        if interval == "1d":
            return fetch_daily(code, tw_market, period=period)
        return fetch_history(code, tw_market, period=period, interval=interval)

    df = load_tw_chart(code, tw_market, period, interval)

    if df.empty:
        st.error("目前抓不到台股行情資料。請稍後再試，或確認股票代號。")
    else:
        last = df.iloc[-1]
        close = float(last["Close"])
        open_ = float(last["Open"])
        change = close - open_
        change_pct = (change / open_ * 100) if open_ else 0

        c1, c2, c3 = st.columns(3)
        c1.metric(f"{tw_market}:{code} 現價", f"{close:.2f}", f"{change:+.2f} ({change_pct:+.2f}%)")
        c2.metric("成交量", f"{int(last['Volume']):,}")
        c3.metric("資料狀態", "公開來源｜可能延遲")

        chart_df = df.copy()
        chart_df["MA5"] = chart_df["Close"].rolling(5).mean()
        chart_df["MA20"] = chart_df["Close"].rolling(20).mean()

        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.04,
            row_heights=[0.75, 0.25]
        )

        fig.add_trace(go.Candlestick(
            x=chart_df.index,
            open=chart_df["Open"],
            high=chart_df["High"],
            low=chart_df["Low"],
            close=chart_df["Close"],
            name="K線"
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=chart_df.index,
            y=chart_df["MA5"],
            mode="lines",
            name="MA5"
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=chart_df.index,
            y=chart_df["MA20"],
            mode="lines",
            name="MA20"
        ), row=1, col=1)

        fig.add_trace(go.Bar(
            x=chart_df.index,
            y=chart_df["Volume"],
            name="成交量"
        ), row=2, col=1)

        fig.update_layout(
            height=720,
            xaxis_rangeslider_visible=False,
            margin=dict(l=10, r=10, t=30, b=10),
            legend_orientation="h"
        )

        st.plotly_chart(fig, use_container_width=True)

    # ---- 台股買入決策 ----
    tw_yahoo = f"{code}.TW" if tw_market == "TWSE" else f"{code}.TWO"
    tw_fund = load_fundamentals_for_decision(tw_yahoo)
    tw_daily_decision = load_daily_history_for_decision(tw_yahoo)

    # institution values are filled later if TWSE data is available; use neutral defaults here.
    tw_inst_score_for_decision = None
    tw_est_cost_for_decision = None

    st.divider()
    st.subheader("台股法人｜推估成本＋集中買進")

    if tw_market == "TWSE":
        @st.cache_data(ttl=300)
        def load_inst(code):
            return fetch_recent(code, trading_days=10)

        inst = load_inst(code)

        if inst.empty:
            st.warning("目前沒有抓到這檔的 TWSE 法人資料。")
        else:
            result = institutional_score(inst)
            latest = inst.iloc[-1]
            concentration = tw_concentration(inst)
            daily_for_cost = fetch_daily(code, tw_market, period="3mo")
            est_cost = estimate_tw_institutional_cost(inst, daily_for_cost)
            current_price = None
            try:
                current_price = float(df["Close"].iloc[-1]) if not df.empty else None
            except Exception:
                current_price = None
            distance_text = "無資料"
            if est_cost and current_price:
                distance_text = f"{(current_price-est_cost)/est_cost*100:+.2f}%"

            tw_decision = build_decision(
                tw_daily_decision,
                tw_fund,
                inst_score=concentration["score"],
                est_cost=est_cost,
                positive_count=concentration["buy_days"],
                negative_count=concentration["sell_days"],
            )
            render_decision_panel(
                "買入決策儀表板",
                tw_decision,
                tw_fund,
                est_cost=est_cost,
            )

            p1, p2, p3, p4 = st.columns(4)
            p1.metric("法人推估成本價", "無資料" if est_cost is None else f"NT${est_cost:.2f}")
            p2.metric("現價距成本", distance_text)
            p3.metric("法人集中買進分數", concentration["score"])
            p4.metric("整體判定", concentration["label"])

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("法人分數", result["score"])
            c2.metric("外資連買", f'{result["foreign_days"]} 日')
            c3.metric("投信連買", f'{result["trust_days"]} 日')
            c4.metric("判定", result["label"])

            st.dataframe(
                pd.DataFrame([{
                    "最新法人日期": str(latest["date"]),
                    "外資": f'{result["foreign"]:,}',
                    "投信": f'{result["trust"]:,}',
                    "自營商": f'{result["dealer"]:,}',
                    "合計": f'{result["total"]:,}',
                }]),
                use_container_width=True,
                hide_index=True
            )

            st.subheader("近 10 日法人加碼 / 減碼")
            st.dataframe(format_tw_history(inst), use_container_width=True, hide_index=True)

            st.caption(
                "台股法人推估成本＝法人淨買超日 Typical Price × 淨買超股數加權估算；"
                "不是法人真正逐筆成交成本。法人日資料為盤後更新。"
            )

            if result["score"] >= 80:
                st.success("法人訊號：高關注法人偏多")
            elif result["score"] >= 60:
                st.info("法人訊號：法人偏多")
            else:
                st.warning(f'法人訊號：{result["label"]}')

            st.caption("法人資料為 TWSE 盤後日報，不是盤中逐筆資料。")
    else:
        st.info("目前 TPEX 上櫃法人資料尚未加入 v0.7。")

else:
    with st.sidebar:
        quick = st.selectbox("快速選擇", list(US_DEFAULTS.keys()))
        tv_symbol = st.text_input("TradingView 代號", value=US_DEFAULTS[quick]).strip().upper()
        tv_interval = st.selectbox("K 線週期", ["1", "5", "15", "30", "60", "D", "W"], index=1)
        theme = st.selectbox("主題", ["dark", "light"], index=0)

    config = {
        "autosize": True,
        "symbol": tv_symbol,
        "interval": tv_interval,
        "timezone": "America/New_York",
        "theme": theme,
        "style": "1",
        "locale": "zh_TW",
        "allow_symbol_change": True,
        "support_host": "https://www.tradingview.com"
    }

    html = f"""
    <div class="tradingview-widget-container" style="height:760px;width:100%">
      <div class="tradingview-widget-container__widget" style="height:calc(100% - 32px);width:100%"></div>
      <div class="tradingview-widget-copyright">
        <a href="https://www.tradingview.com/" rel="noopener nofollow" target="_blank">
          <span class="blue-text">Track all markets on TradingView</span>
        </a>
      </div>
      <script type="text/javascript"
        src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js"
        async>
      {json.dumps(config, ensure_ascii=False)}
      </script>
    </div>
    """

    components.html(html, height=800, scrolling=False)

    st.subheader("美股機構法人｜13F 推估成本參考")

    ticker_only = tv_symbol.split(":", 1)[-1]

    @st.cache_data(ttl=86400)
    def load_us_inst(ticker):
        return institutional_reference_with_fallback(ticker)

    us_inst = load_us_inst(ticker_only)

    # Record latest automatic 13F check time.
    check_now = datetime.now().astimezone()
    st.session_state["last_13f_check"] = check_now

    report_date_now = us_inst.get("latest_report_date")
    if report_date_now:
        st.session_state["last_13f_report_date"] = report_date_now

    st.session_state["last_13f_status"] = us_inst.get("data_status", "最新可取得資料")

    est = us_inst.get("estimated_cost")
    qvwap = us_inst.get("quarter_vwap")
    implied = us_inst.get("implied_report_price")
    report_date = us_inst.get("latest_report_date") or "無資料"
    confidence = us_inst.get("confidence", "低")

    info1, info2 = st.columns(2)
    info1.metric(
        "13F 最後檢查時間",
        st.session_state["last_13f_check"].strftime("%Y-%m-%d %H:%M") if st.session_state.last_13f_check else "尚未檢查"
    )
    info2.metric(
        "最新 13F 申報日期",
        st.session_state.get("last_13f_report_date") or "無資料"
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("法人推估成本價", "無資料" if est is None else f"${est:.2f}")
    c2.metric("近一季 VWAP", "無資料" if qvwap is None else f"${qvwap:.2f}")
    c3.metric("13F申報隱含價", "無資料" if implied is None else f"${implied:.2f}")
    c4.metric("可信度", confidence)

    st.caption(
        f"最新機構申報日期：{report_date}。"
        "13F 不會公開機構真正買進價格；這裡的『推估成本價』是用近一季成交量加權均價 "
        "與機構申報 Value/Shares 的參考價估算，只能當成本區參考。"
    )

    st.caption("此 PWA 版會每天自動重新檢查一次 13F 公開資料；如果最新申報日期有變化，畫面會自動使用新資料重算法人推估成本。")

    holders = us_inst.get("holders")
    if holders is not None and not holders.empty:
        score_info = concentration_score(holders)
        c5, c6, c7 = st.columns(3)
        c5.metric("法人集中買進分數", score_info["score"])
        c6.metric("加碼機構數", score_info["positive"])
        c7.metric("減碼機構數", score_info["negative"])

        if score_info["score"] >= 80:
            st.success(f"法人整體判定：{score_info['label']}")
        elif score_info["score"] >= 60:
            st.info(f"法人整體判定：{score_info['label']}")
        else:
            st.warning(f"法人整體判定：{score_info['label']}")

        st.subheader("主要機構持股變化")
        chinese_holders = format_holders_chinese(holders.head(12))
        st.dataframe(chinese_holders, use_container_width=True, hide_index=True)

        st.caption(
            "綠色代表增持、紅色代表減持；法人集中買進分數會綜合加碼機構數、加碼幅度與持股權重。"
        )

        us_fund = load_fundamentals_for_decision(ticker_only)
        us_daily_decision = load_daily_history_for_decision(ticker_only)
        us_decision = build_decision(
            us_daily_decision,
            us_fund,
            inst_score=score_info["score"],
            est_cost=est,
            positive_count=score_info["positive"],
            negative_count=score_info["negative"],
        )
        render_decision_panel(
            "買入決策儀表板",
            us_decision,
            us_fund,
            est_cost=est,
        )
    else:
        st.info("目前公開來源沒有回傳這檔股票的機構持股明細。")
        us_fund = load_fundamentals_for_decision(ticker_only)
        us_daily_decision = load_daily_history_for_decision(ticker_only)
        us_decision = build_decision(
            us_daily_decision,
            us_fund,
            inst_score=None,
            est_cost=est,
        )
        render_decision_panel(
            "買入決策儀表板",
            us_decision,
            us_fund,
            est_cost=est,
        )

    st.info("美股圖表使用 TradingView Widget；資料是否即時與交易所授權取決於 TradingView。")

st.divider()
st.caption("v2.0：買入決策儀表板；整合趨勢、法人、基本面、估值、動能與風險。")
