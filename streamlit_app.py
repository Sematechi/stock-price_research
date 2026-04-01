import streamlit as st
import requests
import pandas as pd
import io
import time
from datetime import datetime, time as dtime
import pytz

from fetch_stock import (
    is_zaraba,
    fetch_stock_data,
    fetch_monthly_stock_data,
    fmt_date_daily,
    fmt_date_monthly,
)

# ---------------------------------------------------------------
# 設定
# ---------------------------------------------------------------
st.set_page_config(page_title="株価チェッカー", page_icon="📈", layout="centered")
st.title("📈 株価チェッカー")

# 月足用銘柄リストのGoogleスプレッドシートCSVエクスポートURL
MONTHLY_SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1OgR9IX86LYAiN1THdAtwkaBd1-kAfRX4wsxXI1BBgek"
    "/export?format=csv&gid=0"
)

# ---------------------------------------------------------------
# 共通ユーティリティ
# ---------------------------------------------------------------

def load_daily_codes():
    """stock_lists.csv から銘柄コードを読み込む"""
    codes = []
    try:
        with open("stock_lists.csv", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.replace("\t", ",").split(",")
                code = parts[-1].strip()
                if code:
                    codes.append(code)
    except FileNotFoundError:
        st.error("stock_lists.csv が見つかりません。同じディレクトリに配置してください。")
    return codes


def load_monthly_codes():
    """
    GoogleスプレッドシートのCSVエクスポートURLから銘柄コードを取得する。
    シートの最終列に銘柄コードが入っている想定（日足CSVと同じ形式）。
    """
    try:
        resp = requests.get(MONTHLY_SHEET_CSV_URL, timeout=15)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text), header=None, dtype=str)
        codes = []
        for _, row in df.iterrows():
            code = str(row.iloc[-1]).strip()
            if code and code.lower() != "nan":
                codes.append(code)
        return codes
    except Exception as e:
        st.error(f"月足銘柄リストの取得に失敗しました: {e}")
        return []


def render_stock_card(code, name, data, fmt_date_fn, volume_unit="株"):
    """1銘柄のカード表示（日足・月足共通）"""
    st.markdown(f"**■ {code}：{name}**")
    if data:
        st.markdown(f"`{fmt_date_fn(data['date'])}`")
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"始値： **{data['open']}**円")
            st.write(f"高値： **{data['high']}**円")
        with col2:
            st.write(f"安値： **{data['low']}**円")
            st.write(f"終値： **{data['close']}**円")
        st.write(f"出来高： {data['volume']}{volume_unit}")
    else:
        st.markdown("_データ取得失敗_")
    st.divider()


# ---------------------------------------------------------------
# 現在時刻・ザラ場判定
# ---------------------------------------------------------------
jst = pytz.timezone("Asia/Tokyo")
now_jst = datetime.now(jst)
now_str = now_jst.strftime("%Y/%m/%d %H:%M")
zaraba = is_zaraba()

if zaraba:
    st.info(f"🕐 現在 {now_str} JST　｜　ザラ場中 → **前営業日**確定データを表示")
else:
    st.info(f"🕐 現在 {now_str} JST　｜　引け後／休場 → **本日**データを表示")

# ---------------------------------------------------------------
# タブ切り替え
# ---------------------------------------------------------------
tab_daily, tab_monthly = st.tabs(["📅 日足", "📆 月足"])

# ===== 日足タブ =====
with tab_daily:
    st.subheader("日足　場帳")
    if st.button("日足データを取得", type="primary", use_container_width=True, key="btn_daily"):
        codes = load_daily_codes()
        if codes:
            progress = st.progress(0, text="取得中...")
            results = []
            for i, code in enumerate(codes):
                c, name, data = fetch_stock_data(code, zaraba)
                results.append((c, name, data))
                progress.progress((i + 1) / len(codes), text=f"取得中... {i+1}/{len(codes)}")
                time.sleep(0.8)
            progress.empty()

            st.divider()
            for code, name, data in results:
                render_stock_card(code, name, data, fmt_date_daily)

# ===== 月足タブ =====
with tab_monthly:
    st.subheader("月足　場帳")
    st.caption("銘柄リスト：Googleスプレッドシートから自動取得")

    if st.button("月足データを取得", type="primary", use_container_width=True, key="btn_monthly"):
        with st.spinner("銘柄リストを取得中..."):
            codes = load_monthly_codes()

        if codes:
            st.caption(f"銘柄数：{len(codes)} 件")
            progress = st.progress(0, text="取得中...")
            results = []
            for i, code in enumerate(codes):
                c, name, data = fetch_monthly_stock_data(code)
                results.append((c, name, data))
                progress.progress((i + 1) / len(codes), text=f"取得中... {i+1}/{len(codes)}")
                time.sleep(0.8)
            progress.empty()

            st.divider()
            for code, name, data in results:
                render_stock_card(code, name, data, fmt_date_monthly)
