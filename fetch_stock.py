import sys
import re
import json
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, time as dtime
import pytz

sys.stdout.reconfigure(encoding='utf-8')

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}

# Yahoo Finance Japan 専用ヘッダー（Referer付き）
YAHOO_HEADERS = {
    **HEADERS,
    "Referer": "https://finance.yahoo.co.jp/",
    "Sec-Fetch-Site": "same-origin",
}

def is_zaraba():
    """ザラ場中（平日9:00〜15:30 JST）かどうか判定"""
    jst = pytz.timezone("Asia/Tokyo")
    now = datetime.now(jst)
    if now.weekday() >= 5:
        return False
    t = now.time()
    return dtime(9, 0) <= t < dtime(15, 30)


def _get_name(soup, code):
    tag = soup.select_one("div#stockinfo_i1 div.si_i1_1 h2")
    if not tag:
        tag = soup.select_one("h1") or soup.select_one("h2")
    return tag.get_text(strip=True) if tag else code


def _parse_ohlcv(cells):
    """cells[0]=日付, [1]=始値, [2]=高値, [3]=安値, [4]=終値, [7]=出来高"""
    if len(cells) < 8:
        return None
    return {
        "date":   cells[0].get_text(strip=True),
        "open":   cells[1].get_text(strip=True),
        "high":   cells[2].get_text(strip=True),
        "low":    cells[3].get_text(strip=True),
        "close":  cells[4].get_text(strip=True),
        "volume": cells[7].get_text(strip=True),
    }


def fetch_stock_data(code, use_confirmed):
    """
    日足データを取得。
    use_confirmed=True  → stock_kabuka_dwm（確定日足）の最新行
    use_confirmed=False → stock_kabuka0（当日リアルタイム）の最新行
    """
    url = f"https://kabutan.jp/stock/kabuka?code={code}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        name = _get_name(soup, code)

        selector = "table.stock_kabuka_dwm" if use_confirmed else "table.stock_kabuka0"
        table = soup.select_one(selector)
        if not table:
            return code, name, None, f"テーブル未検出: {selector}"

        rows = table.find_all("tr")
        if len(rows) < 2:
            return code, name, None, f"行数不足: {len(rows)}"

        cells = rows[1].find_all(["th", "td"])
        data = _parse_ohlcv(cells)
        if data is None:
            return code, name, None, f"セル数不足: {len(cells)}"
        return code, name, data, None
    except Exception as e:
        return code, code, None, str(e)


def fetch_monthly_stock_data(code):
    """
    月足データを取得（最新の1行＝当月または直近確定月）。
    株探の月足URL: https://kabutan.jp/stock/kabuka?code={code}&ashi=mon
    テーブル: table.stock_kabuka_dwm（日足と同じクラス名、月足ページでは月足データが入る）
    rows[1] が一番上の行（最新月）。
    """
    url = f"https://kabutan.jp/stock/kabuka?code={code}&ashi=mon"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        name = _get_name(soup, code)

        table = soup.select_one("table.stock_kabuka_dwm")
        if not table:
            return code, name, None

        rows = table.find_all("tr")
        # rows[0] = ヘッダー行
        # rows[1] = 最新月（当月進行中 or 直近確定月）
        if len(rows) < 2:
            return code, name, None

        cells = rows[1].find_all(["th", "td"])
        data = _parse_ohlcv(cells)
        return code, name, data
    except Exception:
        return code, code, None


def fmt_date_daily(date_str):
    """YY/MM/DD → 20YY/MM/DD"""
    if len(date_str) == 8 and date_str[2] == '/':
        return "20" + date_str
    return date_str


def fmt_date_monthly(date_str):
    """YY/MM → 20YY/MM（月足用）"""
    if len(date_str) == 5 and date_str[2] == '/':
        return "20" + date_str
    return date_str


def fetch_3month_close(code, pages=3):
    """
    過去3ヶ月分の日足終値を取得。
    Yahoo Finance chart API を優先（Streamlit Cloud でも動作）。
    Yahoo Finance で見つからない場合は kabutan.jp にフォールバック。
    戻り値: (code, name, [ {"date": "20YY/MM/DD", "close": "1234"}, ... ])
            データ取得失敗時は空リスト。
    """
    import datetime as _dt

    # --- Yahoo Finance ---
    yf_url = (
        f"https://query2.finance.yahoo.com/v8/finance/chart/{code}.T"
        f"?interval=1d&range=3mo"
    )
    try:
        resp = requests.get(yf_url, headers=YAHOO_HEADERS, timeout=15)
        resp.raise_for_status()
        result = json.loads(resp.text)
        chart_result = result.get("chart", {}).get("result", [])
        if chart_result:
            chart = chart_result[0]
            timestamps = chart.get("timestamp", [])
            closes = chart.get("indicators", {}).get("quote", [{}])[0].get("close", [])
            if timestamps:
                meta = chart.get("meta", {})
                name = meta.get("longName") or meta.get("shortName") or code
                rows_all = []
                for ts, cl in zip(timestamps, closes):
                    if cl is None:
                        continue
                    date_str = _dt.date.fromtimestamp(ts).strftime("%Y/%m/%d")
                    rows_all.append({
                        "date":  date_str,
                        "close": str(int(round(cl))),
                    })
                rows_all.reverse()  # 新しい順に並べる
                return code, name, rows_all
    except Exception:
        pass

    # --- フォールバック: kabutan.jp ---
    base_url = f"https://kabutan.jp/stock/kabuka?code={code}&ashi=day&page="
    name = code
    rows_all = []
    for page in range(1, pages + 1):
        url = base_url + str(page)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            if page == 1:
                name = _get_name(soup, code)
            table = soup.select_one("table.stock_kabuka_dwm")
            if not table:
                break
            for tr in table.find_all("tr")[1:]:
                cells = tr.find_all(["th", "td"])
                if len(cells) < 5:
                    continue
                date_str = cells[0].get_text(strip=True)
                close_str = cells[4].get_text(strip=True)
                if not date_str or not close_str:
                    continue
                rows_all.append({
                    "date":  fmt_date_daily(date_str),
                    "close": close_str,
                })
        except Exception:
            break
        if page < pages:
            time.sleep(1.0)

    return code, name, rows_all


# ---------------------------------------------------------------
# BPS・配当取得ユーティリティ
# ---------------------------------------------------------------

def _clean_number(text):
    """カンマ・単位（円、%など）を除去してfloatに変換。取得不能時は '-' を返す"""
    if not text:
        return "-"
    # ハイフン・ダッシュのみの文字列はデータなし
    stripped = text.strip()
    if stripped in ("", "-", "--", "---", "－", "ー", "N/A", "n/a"):
        return "-"
    cleaned = re.sub(r'[^\d.\-]', '', stripped.replace(',', ''))
    if not cleaned or cleaned == "-":
        return "-"
    try:
        return float(cleaned)
    except ValueError:
        return "-"


def fetch_bps(code):
    """
    irbank.net (https://irbank.net/{code}) から
    BPS（1株当たり純資産）を取得する。
    "BPS（連）" または "BPS（単）" を含む td の直後の td から値を取得。
    取得失敗時は '-' を返す。
    """
    url = f"https://irbank.net/{code}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # 構造: <dt><a>BPS（連）</a></dt><dd>..936.4円/株..</dd>
        for dt in soup.find_all("dt"):
            if re.search(r'BPS（[連単]）', dt.get_text(strip=True)):
                dd = dt.find_next_sibling("dd")
                if dd:
                    val = _clean_number(dd.get_text(strip=True))
                    if val != "-":
                        return val

        return "-"
    except Exception:
        return "-"


def fetch_dividend(code):
    """
    Yahoo Finance グローバル chart API から配当履歴を取得し、
    直近の確定済み年間配当合計（調整後）を返す。

    ex-dividend date の月から 3月決算の会計年度（FY）を判定して合算。
      month >= 4 → FY = year + 1（例: 2024年8月 → FY2025）
      month <  4 → FY = year  （例: 2025年1月 → FY2025）
    今日時点で終了している最新 FY（FY終了 = 翌年4月1日以降）の合計を返す。
    取得失敗・データなしの場合は '-' を返す。
    """
    import datetime

    url = (
        f"https://query2.finance.yahoo.com/v8/finance/chart/{code}.T"
        f"?interval=3mo&range=6y&events=dividends"
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        result = json.loads(resp.text)

        events = (
            result.get("chart", {})
                  .get("result", [{}])[0]
                  .get("events", {})
                  .get("dividends", {})
        )
        if not events:
            return "-"

        today = datetime.date.today()

        # ex-dividend date ごとに FY を判定して合算
        fy_totals: dict[int, float] = {}
        for ts_str, entry in events.items():
            ex_date = datetime.date.fromtimestamp(int(ts_str))
            fy = ex_date.year + 1 if ex_date.month >= 4 else ex_date.year
            fy_totals[fy] = fy_totals.get(fy, 0.0) + entry["amount"]

        # 3月決算FYの終了日 = 翌年4月1日。それが今日以前なら確定済み
        completed = {
            fy: total for fy, total in fy_totals.items()
            if today >= datetime.date(fy, 4, 1)
        }
        if not completed:
            return "-"

        latest_fy = max(completed)
        return float(round(completed[latest_fy], 2))

    except Exception:
        return "-"


def fetch_monthly_with_extras(code):
    """
    1銘柄につき以下をまとめて取得して返す:
      - 月足の四本値（kabutan.jp）
      - BPS（irbank.net）
      - 直近配当実績（irbank.net）

    Returns:
        dict with keys:
          code, name, date, open, high, low, close, bps, dividend
        取得失敗のフィールドは '-'。
    """
    result = {
        "銘柄コード": code,
        "銘柄名":     code,
        "年月":       "-",
        "始値":       "-",
        "高値":       "-",
        "安値":       "-",
        "終値":       "-",
        "配当実績":   "-",
        "BPS":        "-",
    }

    # 1. 月足四本値
    try:
        _, name, data = fetch_monthly_stock_data(code)
        result["銘柄名"] = name
        if data:
            result["年月"] = fmt_date_monthly(data["date"])
            result["始値"] = _clean_number(data["open"])
            result["高値"] = _clean_number(data["high"])
            result["安値"] = _clean_number(data["low"])
            result["終値"] = _clean_number(data["close"])
    except Exception:
        pass

    time.sleep(2)

    # 2. BPS
    result["BPS"] = fetch_bps(code)
    time.sleep(2)

    # 3. 配当実績
    result["配当実績"] = fetch_dividend(code)
    time.sleep(2)

    return result
