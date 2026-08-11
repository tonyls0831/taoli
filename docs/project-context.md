# Taoli project context

最後更新：2026-08-11

## 專案定位

Taoli 是一個以 Obsidian 為載體的交易策略研究 vault。現有材料聚焦馬克羊（電玩醫生 Dr. 楊震）公開與補充取得的影片內容，將策略主張、逐字稿證據、制度規則、分析判斷、人工 SOP 與公開資料監控工具分層保存。

本專案目前只做研究、監控、計算、報告與通知；不連接券商，也不自動下單。

## Codex 遷移狀態

- Phase 0 已建立 Git baseline：`45bcb6e55f3184257ad92b7db65f0d9efbe27146`。
- Phase 1 已執行 Claude Code chat import；Claude 的本機原始 JSONL 與 memory 仍保留於 `%USERPROFILE%\.claude\projects\D--obsidian-vaults-taoli`，但它們不再是執行期依賴。
- Phase 2 將 Codex 設為主要 agent，專案預設模型為 `gpt-5.6-sol`，推理強度為 `xhigh`。
- Claude 的寬鬆 shell allowlist、一次性暫存路徑與舊 whisper.cpp scratchpad 沒有遷入 Codex。

## 已保存的研究材料

- `transcripts/` 保存 25 支影片的 `.txt` 與 `.srt`：22 支本地收藏加 3 支補充來源。
- `馬克羊交易策略系統性分析.md` 是策略主張、影片對照、分析判斷與限制的主報告。
- `套利操作SOP.md` 把五類機會整理成人工操作流程、觸發條件、出場與失效條件。
- `videos/` 是大型本機來源媒體，刻意不納入 Git；可追蹤的逐字稿才是 repository 內的長期證據層。

逐字稿是語音辨識產物。若結論取決於特定數字、否定詞、時間或逐字引述，必須回查 `.srt` 時間軸並視需要回聽來源影音。

## 主要研究線

1. 颱風假造成結算日順延後的選擇權時間價值重定價。
2. 除權息預估變化造成的台指期遠近月合理價差調整。
3. 股票期貨結算公式衍生的尾盤結算鎖定區間。
4. 結算日期現價差收斂與除權息日行為錯價。
5. 總經事件、機械化當沖與制度化風控。

這些名稱描述的是研究主題，不代表其報酬、容量、流動性或當前有效性已獲保證。完整證據與評估應回到主報告和 SOP。

## 現有工具

`scripts/` 有四支 Python 輔助工具：

- `typhoon_watch.py`：監控停班停課公告。
- `dividend_spread.py`：估算除權息蒸發點數與遠近月價差。
- `settlement_monitor.py`：追蹤結算均價、鎖定區間與選用的期現價差。
- `morning_brief.py`：產出盤前市場與除權息資訊摘要。

它們以公開資料源執行，主要來源包括 DGPA、TWSE OpenAPI、TWSE MIS、TAIFEX 盤後資料、TAIFEX MIS、Yahoo Finance 與 TWSE T86。免費或非正式揭示端點沒有 SLA，頁面格式、憑證、限流與欄位都可能改變。

Claude-era 紀錄顯示四支工具曾於 2026-07-17 對真實資料執行；這只是歷史驗證時間點。任何關鍵日使用前仍須重新做最小 smoke test，並以交易所或政府正式公告作最終依據。

## 本機與機密狀態

- `scripts/config.json` 在第一次執行時產生，可能存放 Discord webhook 或 Telegram token；它被 Git 忽略。
- `data/*_state.json` 是執行狀態，不是研究證據，也被 Git 忽略。
- 通知設定可以留空；console 輸出仍可使用。
- 目前沒有券商 API、帳戶金鑰、下單模組或自動化部位管理。

## 已知限制與重新驗證條件

- 市場規則、結算公式、休市辦法或商品規格變更時，先更新規則前提，再評估程式和 SOP。
- 造市商自動化與策略公開會縮短事件窗口；舊案例的反應時間不能直接外推。
- 遠近月價差模型受未公告除息資訊、預估日變動、利率、避險需求與流動性影響。
- 2026-07-17 曾出現台股急跌而次月價差約 `+250` 點的異常案例；警報可能代表市場狀態異常，而不是可直接進場的機會。
- 公開資料錯誤、延遲或缺漏時，工具應失敗得清楚，不能以舊值假裝即時值。

## 後續工作邊界

- 建立自動化測試與可重播 fixtures，降低對即時端點的驗證依賴。
- 每年颱風季與除權息季前重新驗證資料解析器。
- 若未來評估券商 API 或自動下單，應視為獨立、高風險專案決策，不是現有腳本的自然延伸。
- GitHub issue tracker 尚未可用，因 repository 目前沒有 remote；相關規範見 `docs/agents/issue-tracker.md`。
