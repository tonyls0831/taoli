# 套利 SOP 輔助腳本

配合 [[套利操作SOP]] 使用的四支 Python 腳本。**全部只用公開資料源、不需券商 API**，
負責「監控＋計算＋警報」；下單一律人工（要自動下單需開通券商 API，如永豐 Shioaji，另議）。

## 環境

- Python 3.10+（本機 3.14 已測通過）
- 從 repository 根目錄安裝 tracked runtime dependencies：
  `python -m pip install --disable-pip-version-check -r requirements.txt`
- 第一次執行任一腳本會自動產生 `config.json`；要手機推播就填：
  - `discord_webhook`：Discord 頻道 → 整合 → Webhook → 複製網址（最簡單）
  - 或 `telegram_bot_token` + `telegram_chat_id`
  - 不填也能用（console 顯示＋蜂鳴聲）

## 腳本一覽

| 腳本 | 對應 SOP | 跑法 | 什麼時候跑 |
|---|---|---|---|
| `typhoon_watch.py` | SOP-1 颱風假 | `python typhoon_watch.py --fast` | 颱風可能襲台的**週二 19:40 起**掛著（平時可用預設 30s 間隔） |
| `dividend_spread.py` | SOP-2 遠近月價差 | `python dividend_spread.py` | 除權息季（6–8月）每天收盤後或盤前跑一次 |
| `settlement_monitor.py` | SOP-3/4 結算微結構＋期現收斂 | `python settlement_monitor.py --stock 2603` | **每月第三個週三** 12:25 前開著 |
| `morning_brief.py` | SOP-5 盤前功課 | `python morning_brief.py` | 每個交易日早上 07:00–08:20 |

## 各腳本說明

### typhoon_watch.py（SOP-1）
輪詢人事行政總處「天然災害停止上班及上課情形」官方頁（比刷市長 FB 快且穩），
臺北市出現「停止上班」且非「照常」→ 蜂鳴＋推播，並標注明天是否為週三結算日。
- `--fast` = 2 秒輪詢（颱風夜專用）；`--once` = 測試單抓
- `--once --source-file <fixture.html>` = 離線重播 DGPA HTML；不連網、不建立設定檔、不發通知或蜂鳴，適合 parser regression test
- 同一則公告只警報一次，不會轟炸
- ⚠️ 警報後先人工核對 DGPA 公告日期、適用範圍，以及交易所最新休市與結算安排；警報本身不是交易指示
- ⚠️ 停班公告的表格版面若改版，解析可能失效——每年颱風季前先 `--once` 測一次

離線重播範例：

```powershell
python typhoon_watch.py --once --source-file ..\tests\fixtures\dgpa\taipei_normal.html
```

### dividend_spread.py（SOP-2）
1. 抓 TWSE 除權息預告（只計現金股利；除權不蒸發指數）
2. 收盤價×發行股數 → 全市場市值 → 每點市值 → 每筆除息的蒸發點數
3. 按台指期結算日（第三個週三）分桶算 D_near / D_cross → **合理價差 = −(D_cross＋避險逆價差)**
4. 對照 TAIFEX 盤後實際近/次月收盤價差
5. 兩種警報：合理價差**與上次比跳動 ≥10 點**（＝除息日估計可能跨過結算日邊界，是原策略關注條件）；市場價差**偏離合理值 ≥8 點**
6. 報告寫入 `data/除權息價差_日期.md`，狀態存 `data/dividend_spread_state.json`
- `--replay <case-dir>` = 依 `scenario.json` 與原始 TWSE／TAIFEX fixtures 做離線重播；
  固定資料日期，只輸出 console，不連網、不讀寫設定、報告或狀態，也不蜂鳴或推播
- ⚠️ 只算「已公告」的除權息。次月桶常低估（例：台積電季配息未公告前 D_cross 會偏小），
  警報訊息已附此提醒；馬克羊的完整版還會人工預估未公告的大權值股
- ⚠️ 崩盤日價差會嚴重錯位（2026-07-17 實測：大盤 -6.5%，次月價差 +250 點），
  此時警報只表示市場狀態異常，不能直接解讀為部位條件

離線重播範例：

```powershell
python dividend_spread.py --replay ..\tests\fixtures\dividend_spread\happy_path
```

### settlement_monitor.py（SOP-3/4）
結算日 12:30（不含，第一筆 12:30:05）起每 5 秒抓現貨即時價（TWSE MIS），維護 661 樣本的累計均值與
「剩餘樣本全走漲/跌停」的**鎖定區間**；區間寬 < 1 tick 時警報並顯示模型區間參考。
- `--futures-symbol <TAIFEX代號>` 加開 SOP-4 期現價差監控（>0.5% 警報）
- `--force --max-iter 3` = 盤後測試模式
- `--replay <case-dir>` = 依 `scenario.json` 與原始 TWSE／選用 TAIFEX fixture 時序
  做有界離線重播；不等待、不連網、不讀寫設定或 runtime 資料，也不蜂鳴或推播
- ⚠️ MIS 是免費揭示源，與交易所正式 5 秒快照可能有零星差異；正式結算價以期交所公告為準
- ⚠️ 模型區間不是保證結算價；樣本、tick、資料延遲與正式結算規則都必須人工核對

離線重播範例：

```powershell
python settlement_monitor.py --replay ..\tests\fixtures\settlement_monitor\happy_path
```

### morning_brief.py（SOP-5）
產出當日盤前簡報到 `盤前簡報/日期.md`：美股四大＋台積電 ADR、台指期夜盤收盤、
**今日除息名單**（含參考價與幅度，>10% 標⭐＝SOP-5 觀察股）、三大法人買賣超 Top。
- `--replay <case-dir> --output-dir <safe-dir>` = 依 `scenario.json` 與原始 Yahoo／
  TAIFEX／TWSE fixtures 固定重播時間，將完整簡報寫入明示安全目錄的日期檔名；
  不連網、不讀寫設定、不通知或蜂鳴，也不改寫既有檔案；安全目錄不得位於
  repository 內（包含正式 `盤前簡報/`）
- ⚠️ replay 簡報只驗證資料解析與盤前研究呈現，仍須人工核對現行市場資料與規則；
  不是下單建議或交易授權
- 搭配 SOP-5 人工流程：8:30 看試撮 → **8:43 期貨禁刪單後**判斷開盤合理性

離線重播範例：

```powershell
python morning_brief.py --replay ..\tests\fixtures\morning_brief\happy_path `
  --output-dir $env:TEMP\taoli-morning-brief-replay
```

## 排程建議（Windows 工作排程器）

```powershell
# 盤前簡報：每個工作日 07:10
schtasks /create /tn "taoli_morning_brief" /sc weekly /d MON,TUE,WED,THU,FRI /st 07:10 `
  /tr "python D:\obsidian_vaults\taoli\scripts\morning_brief.py"

# 除權息價差表：每個工作日 15:30
schtasks /create /tn "taoli_dividend_spread" /sc weekly /d MON,TUE,WED,THU,FRI /st 15:30 `
  /tr "python D:\obsidian_vaults\taoli\scripts\dividend_spread.py"
```
颱風監聽與結算監控是「事件日」腳本，建議手動開（颱風夜／第三個週三），不排程。

## 資料源

| 源 | 用途 | 備註 |
|---|---|---|
| dgpa.gov.tw `typh/daily/nds.html` | 停班停課 | 憑證缺 SKI，已用放寬 SSL context（鏈仍驗證） |
| TWSE OpenAPI `TWT48U_ALL` / `t187ap03_L` / `STOCK_DAY_ALL` | 除權息預告／發行股數／收盤 | 免費無限制 |
| TWSE MIS `getStockInfo.jsp` | 現貨/指數即時價 | 非官方公開 API，勿高頻濫打（本腳本 5s） |
| TAIFEX `futDataDown` | 期貨盤後日資料 | Big5 CSV |
| TAIFEX MIS `getQuoteDetail` | 股期即時價（選用） | 最脆弱的一環，失敗自動略過 |
| Yahoo Finance v8 chart | 美股/ADR | 免金鑰 |
| TWSE RWD `T86` | 三大法人 | |

## 已知限制（誠實條款）

1. 這些腳本**輔助人工判斷**，不構成交易訊號的全部——SOP 裡的合理性判斷、
   口數控制、升降級制度都還是人的事。
2. 免費資料源沒有 SLA：頁面改版、被限流都可能發生，關鍵日（颱風夜、結算日）
   請提早開起來確認有在動。
3. 颱風假策略的窗口取決於造市商自動化程度，腳本只能保證「你不會比別人晚知道」，
   不能保證還有肉（見主分析報告的時效性評估）。
