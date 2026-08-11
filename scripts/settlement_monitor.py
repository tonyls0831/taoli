# -*- coding: utf-8 -*-
"""SOP-3/4 結算日監控器：即時結算均價 + 鎖定區間 +（可選）期現價差。

原理：股票期貨結算價 = 結算日 12:30–13:25 現貨每 5 秒快照（660 個）
＋ 13:30 收盤價，共 661 個數字的算術平均。
本腳本每 5 秒抓一次現貨即時價，維護：
  - 目前累計均值 M
  - 鎖定區間 [worst_low, worst_high]：剩餘樣本全走跌停/漲停時最終均值的極限
區間寬 < 1 tick 時（實務 13:10 後）= 結算價已可 100% 確定 → 警報並提示可掛的內側價位。

SOP-4：加 --futures-symbol（TAIFEX MIS 代號，例 CDFH6-F）即同步抓股期報價，
期現價差 > 門檻（%）時警報。

用法：
  python settlement_monitor.py --stock 2603              # 結算日 12:25 前開著
  python settlement_monitor.py --stock 2603 --force      # 非結算日/盤後測試
  python settlement_monitor.py --stock 2603 --futures-symbol DBFH6-F
"""
import argparse
import time
from datetime import datetime, timedelta

from common import (TZ, load_config, make_session, notify, now_taipei,
                    third_wednesday)

MIS_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
TAIFEX_MIS = "https://mis.taifex.com.tw/futures/api/getQuoteDetail"
TOTAL_SAMPLES = 661          # 660 個 5 秒快照 + 收盤價


def tick_size(price: float) -> float:
    for bound, tick in ((10, 0.01), (50, 0.05), (100, 0.1), (500, 0.5), (1000, 1)):
        if price < bound:
            return tick
    return 5.0


def fetch_spot(session, stock: str) -> dict:
    r = session.get(MIS_URL, params={"ex_ch": f"tse_{stock}.tw|otc_{stock}.tw",
                                     "json": "1", "delay": "0"}, timeout=10)
    r.raise_for_status()
    arr = r.json().get("msgArray", [])
    if not arr:
        raise RuntimeError(f"MIS 查不到 {stock}")
    q = arr[0]

    def num(key):
        try:
            return float(q.get(key, ""))
        except (TypeError, ValueError):
            return None

    return {"last": num("z"), "prev_close": num("y"),
            "limit_up": num("u"), "limit_dn": num("w"),
            "name": q.get("n", stock), "time": q.get("t", "")}


def fetch_futures(session, symbol: str) -> float | None:
    try:
        r = session.post(TAIFEX_MIS, json={"SymbolID": symbol}, timeout=10)
        r.raise_for_status()
        d = r.json().get("RtData", {}).get("QuoteList", [])
        node = d[0] if d else r.json().get("RtData", {}).get("Quote", {})
        for k in ("CLastPrice", "CRefPrice", "LastPrice"):
            v = node.get(k)
            if v:
                return float(str(v).replace(",", ""))
    except Exception as e:
        print(f"[warn] 期貨報價抓取失敗: {e}")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock", required=True, help="現貨代號，例 2603")
    ap.add_argument("--futures-symbol", default="", help="TAIFEX MIS 股期代號（選填，SOP-4 用）")
    ap.add_argument("--force", action="store_true", help="忽略結算日/時段檢查（測試）")
    ap.add_argument("--max-iter", type=int, default=0, help="最多抓幾次（0=直到 13:30）")
    args = ap.parse_args()

    cfg = load_config()
    session = make_session()
    today = now_taipei().date()

    settle = third_wednesday(today.year, today.month)
    if today != settle and not args.force:
        print(f"今天 {today} 不是結算日（本月第三個週三 = {settle}）。測試請加 --force")
        return

    q0 = fetch_spot(session, args.stock)
    if not (q0["limit_up"] and q0["limit_dn"]):
        print("[warn] 抓不到漲跌停價，鎖定區間無法計算（收盤後測試屬正常）")
    print(f"[settlement_monitor] {args.stock} {q0['name']}｜昨收 {q0['prev_close']}"
          f"｜漲停 {q0['limit_up']}｜跌停 {q0['limit_dn']}")
    print(f"結算均價 = 12:30–13:25 每 5 秒快照 660 個 + 收盤價，共 {TOTAL_SAMPLES} 個的平均\n")

    start = now_taipei().replace(hour=12, minute=30, second=0, microsecond=0)
    if now_taipei() < start and not args.force:
        wait = (start - now_taipei()).total_seconds()
        print(f"等待 12:30 開始取樣（{wait / 60:.1f} 分鐘）…")
        time.sleep(max(0, wait))

    samples: list[float] = []
    last_price = q0["last"] or q0["prev_close"]
    locked_announced = False
    n_iter = 0

    while True:
        n_iter += 1
        try:
            q = fetch_spot(session, args.stock)
            if q["last"]:
                last_price = q["last"]
        except Exception as e:
            print(f"[warn] {e}")
        samples.append(last_price)             # 無成交時沿用前一筆（與交易所揭示邏輯一致）

        n = len(samples)
        m = sum(samples) / n
        remain = max(TOTAL_SAMPLES - n, 0)
        lu, ld = q0["limit_up"], q0["limit_dn"]
        if lu and ld:
            hi = (sum(samples) + remain * lu) / TOTAL_SAMPLES
            lo = (sum(samples) + remain * ld) / TOTAL_SAMPLES
        else:
            hi = lo = m
        tick = tick_size(last_price)

        stamp = now_taipei().strftime("%H:%M:%S")
        line = (f"[{stamp}] n={n:3d}/{TOTAL_SAMPLES} 價={last_price:.2f} "
                f"均={m:.4f} 鎖定區間=[{lo:.2f}, {hi:.2f}] 寬={hi - lo:.3f}")
        print(line)

        if not locked_announced and lu and ld and (hi - lo) < tick and n > 60:
            locked_announced = True
            inner_lo = round((int(lo / tick)) * tick, 2)
            inner_hi = round(inner_lo + tick, 2)
            notify("🔒 SOP-3 結算價區間鎖定",
                   f"{args.stock} {q0['name']} 結算價已鎖定 ≈ [{lo:.2f}, {hi:.2f}]\n"
                   f"→ 區間內側參考：低於 {inner_lo} 的買單穩賺、高於 {inner_hi} 的賣單穩賺\n"
                   f"（有人在區間外側成交＝送錢；絕不掛區間外側單）", cfg)

        if args.futures_symbol:
            fp = fetch_futures(session, args.futures_symbol)
            if fp and last_price:
                basis = last_price - fp
                pct = basis / last_price * 100
                print(f"          期貨 {fp:.2f}｜期現價差 {basis:+.2f}（{pct:+.2f}%）")
                if abs(pct) >= float(cfg.get("basis_alert_pct", 0.5)):
                    notify("↔️ SOP-4 期現價差擴大",
                           f"{args.stock} 現貨 {last_price:.2f} vs 期貨 {fp:.2f} "
                           f"= {basis:+.2f}（{pct:+.2f}%）\n"
                           f"現貨急{'漲' if basis > 0 else '跌'}、期貨貼均值落後 → "
                           f"檢視 {'空現貨＋買期貨' if basis > 0 else '買現貨＋空期貨'}，"
                           f"收斂 <0.5 元雙平", cfg, sound=not locked_announced)

        end = now_taipei().replace(hour=13, minute=30, second=10, microsecond=0)
        if (args.max_iter and n_iter >= args.max_iter) or (now_taipei() > end and not args.force) \
                or (args.force and args.max_iter == 0 and n_iter >= 12):
            break
        time.sleep(5)

    print(f"\n最終估計均值 {sum(samples) / len(samples):.4f}（樣本 {len(samples)} 筆）")
    print("提醒：正式結算價以期交所公告為準（含收盤價那一筆）。")


if __name__ == "__main__":
    main()
