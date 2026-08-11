# -*- coding: utf-8 -*-
"""共用工具：HTTP、通知、日期、設定。所有腳本 import 這裡。"""
import json
import ssl
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter, Retry

TZ = ZoneInfo("Asia/Taipei")
SCRIPT_DIR = Path(__file__).resolve().parent
VAULT_DIR = SCRIPT_DIR.parent          # scripts/ 放在 vault 根目錄下
DATA_DIR = VAULT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
}

DEFAULT_CONFIG = {
    "discord_webhook": "",
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "hedge_discount_points": 5,     # SOP-2 避險逆價差（點）
    "spread_jump_alert": 10,        # SOP-2 合理價差跳動警報門檻（點）
    "spread_gap_alert": 8,          # SOP-2 市場價差 vs 合理價差 落差警報門檻（點）
    "basis_alert_pct": 0.5,         # SOP-4 期現價差警報門檻（%）
}


def configure_console_encoding() -> None:
    """Keep Chinese text and symbols printable in Windows CP950 consoles."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


configure_console_encoding()


def load_config() -> dict:
    cfg_path = SCRIPT_DIR / "config.json"
    cfg = dict(DEFAULT_CONFIG)
    if cfg_path.exists():
        try:
            cfg.update(json.loads(cfg_path.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"[warn] config.json 讀取失敗，使用預設值: {e}")
    else:
        cfg_path.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print(f"[info] 已建立預設設定檔 {cfg_path}（要推播請填 discord_webhook 或 telegram_*）")
    return cfg


class RelaxedSSLAdapter(HTTPAdapter):
    """政府網站憑證常缺 Subject Key Identifier，Python 3.13+ 嚴格模式會拒絕。
    這裡只放寬「嚴格檢查」，憑證鏈本身仍會驗證。"""

    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


def make_session(relaxed_ssl_hosts: tuple[str, ...] = ()) -> requests.Session:
    s = requests.Session()
    s.headers.update(UA)
    retry = Retry(total=3, backoff_factor=1.5,
                  status_forcelist=(500, 502, 503, 504),
                  allowed_methods=None)
    s.mount("https://", HTTPAdapter(max_retries=retry))
    for host in relaxed_ssl_hosts:
        s.mount(f"https://{host}/", RelaxedSSLAdapter(max_retries=retry))
    return s


# ---------------------------------------------------------------- 通知

def beep(times: int = 3):
    if sys.platform == "win32":
        try:
            import winsound
            for _ in range(times):
                winsound.Beep(1200, 400)
                time.sleep(0.1)
        except Exception:
            print("\a" * times, end="", flush=True)
    else:
        print("\a" * times, end="", flush=True)


def notify(title: str, message: str, cfg: dict | None = None, sound: bool = True):
    """console + 蜂鳴 + Discord webhook / Telegram（設定了才發）。"""
    cfg = cfg or {}
    stamp = datetime.now(TZ).strftime("%H:%M:%S")
    print(f"\n{'=' * 60}\n[{stamp}] ** {title} **\n{message}\n{'=' * 60}")
    if sound:
        beep()
    text = f"**{title}**\n{message}"
    hook = cfg.get("discord_webhook")
    if hook:
        try:
            requests.post(hook, json={"content": text[:1900]}, timeout=10)
        except Exception as e:
            print(f"[warn] Discord 推播失敗: {e}")
    tok, chat = cfg.get("telegram_bot_token"), cfg.get("telegram_chat_id")
    if tok and chat:
        try:
            requests.get(f"https://api.telegram.org/bot{tok}/sendMessage",
                         params={"chat_id": chat, "text": f"{title}\n{message}"[:4000]},
                         timeout=10)
        except Exception as e:
            print(f"[warn] Telegram 推播失敗: {e}")


# ---------------------------------------------------------------- 日期

def roc_to_date(roc: str) -> date | None:
    """'1150722' -> date(2026, 7, 22)；解析失敗回 None。"""
    roc = (roc or "").strip().replace("/", "")
    if not roc.isdigit() or len(roc) < 6:
        return None
    y, m, d = int(roc[:-4]) + 1911, int(roc[-4:-2]), int(roc[-2:])
    try:
        return date(y, m, d)
    except ValueError:
        return None


def third_wednesday(year: int, month: int) -> date:
    d = date(year, month, 1)
    # weekday(): Mon=0 ... Wed=2
    offset = (2 - d.weekday()) % 7
    return d + timedelta(days=offset + 14)


def settlement_dates_from(today: date, n: int = 3) -> list[date]:
    """回傳從今天起的 n 個台指期（月）結算日（第三個週三；未處理颱風假順延）。"""
    out, y, m = [], today.year, today.month
    while len(out) < n:
        s = third_wednesday(y, m)
        if s >= today:
            out.append(s)
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def contract_code(d: date) -> str:
    return f"{d.year}{d.month:02d}"


def now_taipei() -> datetime:
    return datetime.now(TZ)
