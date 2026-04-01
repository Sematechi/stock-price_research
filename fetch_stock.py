import sys
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
        "Chrome/120.0.0.0 Safari/537.36"
    )
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
            return code, name, None

        rows = table.find_all("tr")
        if len(rows) < 2:
            return code, name, None

        cells = rows[1].find_all(["th", "td"])
        data = _parse_ohlcv(cells)
        return code, name, data
    except Exception:
        return code, code, None


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
    株探の日足時系列ページを page=1〜pages までスクレイピング。
    戻り値: (code, name, [ {"date": "20YY/MM/DD", "close": "1234"}, ... ])
            データ取得失敗時は空リスト。
    """
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

            for tr in table.find_all("tr")[1:]:  # 先頭はヘッダー行
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
