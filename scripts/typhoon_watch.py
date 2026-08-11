# -*- coding: utf-8 -*-
"""SOP-1 颱風假停班停課監聽器。

輪詢人事行政總處「天然災害停止上班及上課情形」頁面，
臺北市出現「停止上班」訊息時發出事件警報（蜂鳴＋推播）。

用法：
  python typhoon_watch.py            # 30 秒輪詢一次（平時掛著）
  python typhoon_watch.py --fast    # 2 秒輪詢一次（週二晚上 19:40 起開這個）
  python typhoon_watch.py --once    # 只抓一次、印出目前狀態（測試用）

搭配 SOP-1：警報後由使用者重新核對正式公告、交易規則與風險；程式不提供下單指示。
"""
import argparse
import hashlib
import time
from datetime import timedelta

from bs4 import BeautifulSoup

from common import load_config, make_session, notify, now_taipei

URL = "https://www.dgpa.gov.tw/typh/daily/nds.html"
TARGETS = ("臺北市", "台北市")   # 判斷基準＝台北市（北北基實務同步）


def fetch_status(session) -> dict[str, str]:
    """回傳 {縣市: 公告文字}。頁面無訊息時回空 dict。"""
    r = session.get(URL, timeout=10)
    r.raise_for_status()
    r.encoding = "utf-8"
    soup = BeautifulSoup(r.text, "html.parser")
    out: dict[str, str] = {}
    for tr in soup.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(cells) >= 2 and cells[0]:
            out[cells[0]] = " ".join(c for c in cells[1:] if c)
    return out


def taipei_alert_text(status: dict[str, str]) -> str | None:
    """臺北市有「停止上班」且非「照常」→ 回傳公告文字，否則 None。"""
    for name in TARGETS:
        for city, text in status.items():
            if name in city and "停止上班" in text and "照常上班" not in text:
                return f"{city}：{text}"
    return None


def settlement_context() -> str:
    now = now_taipei()
    tomorrow = now.date() + timedelta(days=1)
    notes = []
    if tomorrow.weekday() == 2:  # 明天週三＝台指週選結算日
        notes.append("⚡ 明天是週三＝台指週選結算日；若公告影響交易日，請核對交易所最新結算安排")
    elif now.weekday() == 2:
        notes.append("今天是週三結算日；若公告影響交易，請核對交易所最新休市與結算安排")
    else:
        notes.append(f"明天是{'一二三四五六日'[tomorrow.weekday()]}，非週三結算日；記錄事件並核對適用商品規則")
    return "\n".join(notes)


def build_alert_message(alert: str) -> str:
    return (
        f"{alert}\n{settlement_context()}\n"
        "→ 人工核對：確認 DGPA 公告的日期與適用範圍，並查核交易所最新休市及結算安排。\n"
        "本警報只表示公告條件被偵測到，不代表任何交易或下單指示。"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=30, help="輪詢間隔（秒）")
    ap.add_argument("--fast", action="store_true", help="2 秒輪詢（颱風夜用）")
    ap.add_argument("--once", action="store_true", help="抓一次就結束（測試）")
    args = ap.parse_args()
    interval = 2 if args.fast else args.interval

    cfg = load_config()
    session = make_session(relaxed_ssl_hosts=("www.dgpa.gov.tw",))

    print(f"[typhoon_watch] 監聽 {URL}")
    print(f"[typhoon_watch] 間隔 {interval}s | {settlement_context()}")

    fired_hash = None      # 已警報過的公告內容 hash（同一公告不重複轟炸）
    fail_streak = 0

    while True:
        try:
            status = fetch_status(session)
            fail_streak = 0
            alert = taipei_alert_text(status)
            stamp = now_taipei().strftime("%H:%M:%S")
            if alert:
                h = hashlib.md5(alert.encode()).hexdigest()
                if h != fired_hash:
                    fired_hash = h
                    notify("🌀 颱風假事件警報 — 請人工核對",
                           build_alert_message(alert), cfg)
                else:
                    print(f"[{stamp}] 臺北市停班公告持續中（已警報過）")
            else:
                tpe = next((f"{c}: {t}" for c, t in status.items()
                            if any(n in c for n in TARGETS)), "（頁面目前無臺北市列）")
                print(f"[{stamp}] 無停班訊息 | {tpe[:60]}")
        except Exception as e:
            fail_streak += 1
            print(f"[warn] 抓取失敗 x{fail_streak}: {type(e).__name__}: {e}")
            if fail_streak == 10:
                notify("typhoon_watch 連續抓取失敗", f"已連續失敗 {fail_streak} 次，請檢查網路/頁面", cfg)

        if args.once:
            break
        time.sleep(interval)


if __name__ == "__main__":
    main()
