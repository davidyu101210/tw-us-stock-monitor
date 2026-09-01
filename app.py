import pandas as pd, plotly.graph_objects as go, streamlit as st
from plotly.subplots import make_subplots
from streamlit_autorefresh import st_autorefresh
from src.market_utils import market_status,yahoo_symbol
from src.providers.market_data import fetch_history,fetch_info
from src.providers.twse import fetch_recent
from src.providers.us_institutional import get_reference,concentration_score,format_holders
from src.decision import build_score

st.set_page_config(page_title="台美股買入決策",page_icon="📈",layout="wide")
st_autorefresh(interval=60000,key="refresh")

st.markdown("""<style>@media(max-width:768px){.block-container{padding:.7rem}.stDataFrame{font-size:.78rem}h1{font-size:1.55rem!important}[data-testid="stMetricValue"]{font-size:1.3rem!important}section[data-testid="stSidebar"]{width:82vw!important;min-width:82vw!important}}</style>""",unsafe_allow_html=True)

st.title("📈 台股＋美股買入決策")
st.caption("Clean v3｜行情、法人、基本面、估值、技術面、風險一次整合")

with st.sidebar:
    market=st.radio("市場",["台股","美股"],horizontal=True)
    if market=="台股":
        tw_market=st.selectbox("市場別",["TWSE","TPEX"]); code=st.text_input("股票代號","2330").strip()
        symbol=yahoo_symbol("TW",code,tw_market); display=f"{tw_market}:{code}"
    else:
        code=st.text_input("美股代號","AAPL").strip().upper(); symbol=code; display=code
    interval_label=st.selectbox("K線",["日 K","60 分","30 分","15 分","5 分"])

status,desc=market_status("TW" if market=="台股" else "US")
a,b=st.columns(2); a.metric("市場狀態",status); b.metric("交易時段",desc)

@st.cache_data(ttl=60)
def chart(symbol,label,market):
    if label=="日 K": return fetch_history(symbol,"1y","1d",market=="美股")
    period,iv={"60 分":("1mo","60m"),"30 分":("5d","30m"),"15 分":("5d","15m"),"5 分":("5d","5m")}[label]
    return fetch_history(symbol,period,iv,market=="美股")

@st.cache_data(ttl=900)
def daily(symbol): return fetch_history(symbol,"1y","1d",False)

@st.cache_data(ttl=1800)
def info(symbol): return fetch_info(symbol)

cdf=chart(symbol,interval_label,market); ddf=daily(symbol); inf=info(symbol)
if cdf.empty:
    st.error("目前抓不到行情，請確認代號或稍後再試。"); st.stop()

last=cdf.iloc[-1]; price=float(last["Close"]); op=float(last["Open"]) if pd.notna(last["Open"]) else price
st.subheader(f"{display}｜{inf.get('name','')}")
q1,q2,q3=st.columns(3); q1.metric("現價",f"{price:.2f}",f"{price-op:+.2f} ({((price-op)/op*100 if op else 0):+.2f}%)"); q2.metric("成交量",f"{int(last['Volume']):,}"); q3.metric("行情來源","公開免費來源｜可能延遲")

x=cdf.copy(); x["MA20"]=x["Close"].rolling(20).mean(); x["MA60"]=x["Close"].rolling(60).mean()
fig=make_subplots(rows=2,cols=1,shared_xaxes=True,vertical_spacing=.04,row_heights=[.75,.25])
fig.add_trace(go.Candlestick(x=x.index,open=x["Open"],high=x["High"],low=x["Low"],close=x["Close"],name="K線"),row=1,col=1)
fig.add_trace(go.Scatter(x=x.index,y=x["MA20"],name="MA20"),row=1,col=1); fig.add_trace(go.Scatter(x=x.index,y=x["MA60"],name="MA60"),row=1,col=1)
fig.add_trace(go.Bar(x=x.index,y=x["Volume"],name="成交量"),row=2,col=1); fig.update_layout(height=650,xaxis_rangeslider_visible=False,margin=dict(l=5,r=5,t=30,b=5),legend_orientation="h")
st.plotly_chart(fig,use_container_width=True)

inst_score=est_cost=positive_count=negative_count=None
st.divider(); st.subheader("🏦 法人 / 機構")
if market=="台股":
    if tw_market=="TWSE":
        @st.cache_data(ttl=300)
        def twinst(code): return fetch_recent(code,10)
        inst=twinst(code)
        if inst.empty: st.warning("目前抓不到 TWSE 三大法人資料。")
        else:
            total=pd.to_numeric(inst["total_net"],errors="coerce").fillna(0); positive_count=int((total>0).sum()); negative_count=int((total<0).sum())
            inst_score=min((25 if positive_count>=3 else 0)+(20 if positive_count>=5 else 0)+(25 if len(total.tail(3))==3 and (total.tail(3)>0).all() else 0)+(20 if len(total.tail(5))==5 and (total.tail(5)>0).all() else 0)+(10 if float(total.iloc[-1])>0 else 0),100)
            px=ddf.reset_index().copy(); px["date_key"]=pd.to_datetime(px.iloc[:,0],errors="coerce").dt.date
            ii=inst.copy(); ii["date_key"]=pd.to_datetime(ii["date"],errors="coerce").dt.date; mrg=ii.merge(px[["date_key","High","Low","Close"]],on="date_key",how="inner")
            if not mrg.empty:
                mrg["tp"]=(mrg["High"]+mrg["Low"]+mrg["Close"])/3; mrg["w"]=pd.to_numeric(mrg["total_net"],errors="coerce").clip(lower=0); used=mrg[(mrg["w"]>0)&mrg["tp"].notna()]
                if not used.empty and used["w"].sum()>0: est_cost=float((used["tp"]*used["w"]).sum()/used["w"].sum())
            c1,c2,c3,c4=st.columns(4); c1.metric("法人集中分數",f"{inst_score}/100"); c2.metric("近10日加碼",positive_count); c3.metric("近10日減碼",negative_count); c4.metric("法人推估成本","無資料" if est_cost is None else f"NT${est_cost:.2f}")
            show=inst.copy(); show["date"]=show["date"].astype(str); show["判定"]=show["total_net"].map(lambda v:"🟢 加碼" if v>0 else ("🔴 減碼" if v<0 else "⚪ 持平")); show=show.rename(columns={"date":"日期","foreign_net":"外資","trust_net":"投信","dealer_net":"自營商","total_net":"合計"})
            st.dataframe(show,use_container_width=True,hide_index=True)
            st.caption("台股法人為 TWSE 盤後日報；推估成本不是實際逐筆成本。")
    else: st.info("TPEX 法人資料暫未加入。")
else:
    @st.cache_data(ttl=86400)
    def usinst(symbol): return get_reference(symbol)
    u=usinst(symbol); holders=u.get("holders"); sc=concentration_score(holders); inst_score=sc["score"]; positive_count=sc["positive"]; negative_count=sc["negative"]; est_cost=u.get("estimated_cost")
    c1,c2,c3,c4=st.columns(4); c1.metric("機構集中分數",f"{inst_score}/100"); c2.metric("加碼機構",positive_count); c3.metric("減碼機構",negative_count); c4.metric("機構推估成本","無資料" if est_cost is None else f"${est_cost:.2f}")
    st.write(f"資料狀態：**{u.get('data_status','未知')}**｜最新申報日期：**{u.get('latest_report_date') or '無資料'}**")
    if u.get("is_fallback"): st.warning("目前沒有新 13F，沿用上一筆成功資料。")
    f=format_holders(holders); st.dataframe(f.head(12),use_container_width=True,hide_index=True) if not f.empty else st.info("目前沒有可顯示的機構持股資料。")
    st.caption("13F 不公開真實買進價格；推估成本只能視為成本區參考。")

st.divider(); st.subheader("🎯 買入決策儀表板")
d=build_score(ddf,inf,inst_score,est_cost,positive_count,negative_count); s=d["snapshot"]
rref=s["price"]-2*s["atr14"] if s.get("price") and s.get("atr14") else None
c1,c2,c3=st.columns(3); c1.metric("綜合分數",f"{d['score']}/100"); c2.metric("目前判定",d["label"]); c3.metric("ATR 2倍風險參考","無資料" if rref is None else f"{rref:.2f}")
st.progress(max(0,min(d["score"],100))/100)
st.dataframe(pd.DataFrame([{"技術趨勢":f"{d['technical']}/25","法人籌碼":f"{d['institutional']}/20","基本面":f"{d['fundamentals']}/20","估值":f"{d['valuation']}/15","動能":f"{d['momentum']}/10","風險控制":f"{d['risk']}/10"}]),use_container_width=True,hide_index=True)
l,r=st.columns(2)
with l:
    st.markdown("#### ✅ 買入理由")
    for z in d["reasons"]: st.write("• "+z)
with r:
    st.markdown("#### ⚠️ 不買 / 等待理由")
    for z in d["risks"]: st.write("• "+z)
st.markdown("#### 關鍵位置")
st.dataframe(pd.DataFrame([{"現價":s.get("price"),"MA20":s.get("ma20"),"MA60":s.get("ma60"),"MA120":s.get("ma120"),"20日支撐":s.get("low20"),"20日壓力":s.get("high20"),"RSI14":s.get("rsi14"),"法人/機構推估成本":est_cost}]).round(2),use_container_width=True,hide_index=True)
def pct(v):
    try:return f"{float(v)*100:.1f}%"
    except Exception:return "無資料"
st.markdown("#### 基本面 / 估值")
st.dataframe(pd.DataFrame([{"營收成長":pct(inf.get("revenue_growth")),"獲利成長":pct(inf.get("earnings_growth")),"毛利率":pct(inf.get("gross_margin")),"ROE":pct(inf.get("roe")),"P/E":inf.get("trailing_pe"),"Forward P/E":inf.get("forward_pe"),"P/B":inf.get("price_to_book"),"PEG":inf.get("peg")}]),use_container_width=True,hide_index=True)
st.info("這是決策輔助工具，不保證獲利，也不是個人化投資建議。免費公開行情、基本面、法人與 13F 資料都可能延遲或缺漏。")
