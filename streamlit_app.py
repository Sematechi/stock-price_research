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
    fetch_3month_close,
    fetch_monthly_with_extras,
    fmt_date_daily,
    fmt_date_monthly,
)

# ---------------------------------------------------------------
# 設定
# ---------------------------------------------------------------
st.set_page_config(page_title="株価チェッカー", page_icon="📈", layout="centered")
st.title("📈 株価チェッカー")

# 日足用銘柄リストのGoogleスプレッドシートCSVエクスポートURL
DAILY_SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1i7mHdfkMreZ_ayoOMYTykBRyagA--0D_JSBCx5ZPjQY"
    "/export?format=csv&gid=0"
)

# 月足用銘柄リストのGoogleスプレッドシートCSVエクスポートURL
MONTHLY_SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1OgR9IX86LYAiN1THdAtwkaBd1-kAfRX4wsxXI1BBgek"
    "/export?format=csv&gid=0"
)

# 過去3ヶ月折れ線用銘柄リストのGoogleスプレッドシートCSVエクスポートURL
THREEMONTH_SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1HJ-95gGC9p5jKC0bd_YdLoqNI55tM6W2aJD5Nu0RerU"
    "/export?format=csv&gid=0"
)

# ---------------------------------------------------------------
# 共通ユーティリティ
# ---------------------------------------------------------------

def load_daily_codes():
    """GoogleスプレッドシートのCSVエクスポートURLから銘柄コードを取得する"""
    try:
        resp = requests.get(DAILY_SHEET_CSV_URL, timeout=15)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text), header=None, dtype=str)
        codes = []
        for _, row in df.iterrows():
            code = str(row.iloc[-1]).strip()
            if code and code.lower() != "nan":
                codes.append(code)
        return codes
    except Exception as e:
        st.error(f"日足銘柄リストの取得に失敗しました: {e}")
        return []


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


def load_threemonth_codes():
    """過去3ヶ月折れ線用の銘柄コードをスプレッドシートから取得する"""
    try:
        resp = requests.get(THREEMONTH_SHEET_CSV_URL, timeout=15)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text), header=None, dtype=str)
        codes = []
        for _, row in df.iterrows():
            code = str(row.iloc[0]).strip()
            if code and code.lower() != "nan":
                codes.append(code)
        return codes
    except Exception as e:
        st.error(f"銘柄リストの取得に失敗しました: {e}")
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
tab_daily, tab_monthly, tab_3month, tab_extras = st.tabs([
    "📅 日足(場帳)", "📆 月足", "📈 過去3ヶ月(折れ線用)", "📊 月足＋配当・BPS"
])

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

            # CSVダウンロード
            csv_rows = []
            for code, name, data in results:
                if data:
                    csv_rows.append({
                        "銘柄コード": code,
                        "銘柄名":     name,
                        "日付":       fmt_date_daily(data["date"]),
                        "始値":       data["open"],
                        "高値":       data["high"],
                        "安値":       data["low"],
                        "終値":       data["close"],
                        "出来高":     data["volume"],
                    })
            if csv_rows:
                csv_bytes = pd.DataFrame(csv_rows).to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                st.download_button("CSVでダウンロード", csv_bytes, "daily.csv", "text/csv")

# ===== 過去3ヶ月タブ =====
with tab_3month:
    st.subheader("過去3ヶ月　日足終値一覧")
    st.caption("銘柄リスト：Googleスプレッドシートから自動取得")

    if st.button("データを取得", type="primary", use_container_width=True, key="btn_3month"):
        with st.spinner("銘柄リストを取得中..."):
            codes = load_threemonth_codes()

        if codes:
            st.caption(f"銘柄数：{len(codes)} 件")
            progress = st.progress(0, text="取得中...")
            results = []
            for i, code in enumerate(codes):
                c, name, rows = fetch_3month_close(code, pages=3)
                results.append((c, name, rows))
                progress.progress((i + 1) / len(codes), text=f"取得中... {i+1}/{len(codes)}")
                time.sleep(0.8)
            progress.empty()

            st.divider()
            csv_rows_3m = []
            for code, name, rows in results:
                st.markdown(f"**■ {code}：{name}**")
                if rows:
                    df = pd.DataFrame(rows).rename(columns={"date": "日付", "close": "終値"})
                    st.dataframe(df, use_container_width=True, hide_index=True)
                    for r in rows:
                        csv_rows_3m.append({"銘柄コード": code, "銘柄名": name, "日付": r["date"], "終値": r["close"]})
                else:
                    st.markdown("_データ取得失敗_")
                st.divider()

            # CSVダウンロード
            if csv_rows_3m:
                csv_bytes_3m = pd.DataFrame(csv_rows_3m).to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                st.download_button("CSVでダウンロード", csv_bytes_3m, "3month_close.csv", "text/csv")

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

# ===== 月足＋配当・BPS タブ =====
with tab_extras:
    st.subheader("月足＋配当実績・BPS 一覧")
    st.caption(
        "銘柄リスト：月足用 Googleスプレッドシートから自動取得  "
        "｜  データ取得元：株探（月足四本値）・Yahoo Finance Japan（BPS・配当）"
    )
    st.info(
        "1銘柄あたり3回リクエスト（待機2秒×3）のため、銘柄数が多い場合は時間がかかります。",
        icon="⏳",
    )

    # デバッグ：1銘柄だけ生HTMLを確認
    debug_code = st.text_input("デバッグ用銘柄コード（空欄でスキップ）", value="", key="debug_code")
    if st.button("デバッグ確認", key="btn_debug") and debug_code.strip():
        import requests as _req
        from fetch_stock import HEADERS
        code_d = debug_code.strip()
        for label, url in [
            ("BPS (irbank)", f"https://irbank.net/{code_d}"),
            ("Dividend (irbank)", f"https://irbank.net/{code_d}/dividend"),
        ]:
            try:
                r = _req.get(url, headers=HEADERS, timeout=15)
                st.markdown(f"**{label}** — status: `{r.status_code}` | len: `{len(r.text)}`")
                # BPSページ用チェック
                import re as _re
                bps_match = _re.search(r'BPS.{0,100}?(\d[\d,]+\.?\d*)円/株', r.text)
                gokei_match = _re.search(r'合計.{0,200}?(\d[\d,]+\.?\d*)', r.text, _re.DOTALL)
                st.markdown(
                    f"- BPS数値マッチ: `{bps_match.group(1) if bps_match else 'なし'}`  "
                    f"- 合計数値マッチ: `{gokei_match.group(1) if gokei_match else 'なし'}`"
                )
                with st.expander("BPS周辺テキスト"):
                    idx = r.text.find("BPS")
                    st.code(r.text[max(0,idx-50):idx+300] if idx >= 0 else "BPS not found")
                with st.expander("合計周辺テキスト"):
                    idx2 = r.text.find("合計")
                    st.code(r.text[max(0,idx2-50):idx2+500] if idx2 >= 0 else "合計 not found")
                # 配当ページ専用: 実績行の詳細
                if "dividend" in url:
                    from bs4 import BeautifulSoup as _BS
                    soup_d = _BS(r.text, "html.parser")
                    for tbl in soup_d.find_all("table"):
                        ths = [th.get_text(strip=True) for th in tbl.find_all("th")]
                        if "合計" not in ths:
                            continue
                        all_rows = tbl.find_all("tr")[1:]
                        st.write(f"テーブルヘッダー: {ths} / 総行数: {len(all_rows)}")
                        for tr in all_rows[-20:]:
                            cells = tr.find_all(["td","th"])
                            st.write([c.get_text(strip=True) for c in cells])
                        break
            except Exception as e:
                st.error(f"{label}: {e}")
            time.sleep(2)

    if st.button("データを取得", type="primary", use_container_width=True, key="btn_extras"):
        with st.spinner("銘柄リストを取得中..."):
            codes = load_monthly_codes()

        if codes:
            st.caption(f"銘柄数：{len(codes)} 件")
            progress = st.progress(0, text="取得中...")
            rows = []
            for i, code in enumerate(codes):
                progress.progress(
                    (i + 1) / len(codes),
                    text=f"取得中... {i + 1}/{len(codes)}  ({code})",
                )
                row = fetch_monthly_with_extras(code)
                rows.append(row)
            progress.empty()

            df = pd.DataFrame(rows, columns=[
                "銘柄コード", "銘柄名", "年月",
                "始値", "高値", "安値", "終値",
                "配当実績", "BPS",
            ])

            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
            )

            # CSVダウンロードボタン
            csv_bytes = df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button(
                label="CSVでダウンロード",
                data=csv_bytes,
                file_name="monthly_bps_dividend.csv",
                mime="text/csv",
            )
