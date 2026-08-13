# Repository governance

最後驗證：2026-08-13

本文件記錄 `tonyls0831/taoli` 的工程入口、`main` 保護政策與實際可用狀態。它不含
GitHub credential 或 token 值。

## Request 與 implementation 入口

- GitHub Issues 是需求與 PRD 的正式入口；使用 `.github/ISSUE_TEMPLATE/engineering-task.yml`
  記錄 objective、spec／evidence、public seam、validation、安全與外部寫入授權。
- Pull request 只實作已 triage 的 Issue，不作為未經規格確認的新需求入口；
  `.github/pull_request_template.md` 要求 linked Issue、seam、驗證、安全與限制。
- Issue 狀態與操作慣例仍以 `docs/agents/issue-tracker.md` 為準。

## Owner 核准的 `main` policy

Issue #11 於 2026-08-13 核准：

- 合併前必須經 pull request，且 `Python 3.10`、`Python 3.14` checks 通過；branch
  必須與 base 保持最新。
- required approving reviews 為 0；solo owner 可在 checks 與 Standards + Spec review
  通過後自行合併。
- owner／administrator 無 required-check bypass。
- 禁止 force push 與刪除 `main`；不增加 code-owner、signed-commit、linear-history 或
  push-restriction 規則。

## 2026-08-13 before／attempted-after evidence

變更前以 GitHub REST API 確認 repository 為 private；squash、merge commit、rebase merge
皆允許，`delete_branch_on_merge` 為 false。讀取 `main` branch protection 與 repository
rulesets 均回傳 HTTP 403：目前帳號方案須升級 GitHub Pro，或把 repository 改為 public，
才能在 private repository 使用這兩項功能。因此本次無法建立 protection/ruleset，
也沒有可聲稱為「failed checks 確實阻擋 merge」的 after evidence。

GitHub 官方文件同樣說明：GitHub Free 可在 public repository 使用 protected branches／
rulesets；private repository 需要 GitHub Pro、Team 或 Enterprise。參考：

- <https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches>
- <https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets>

## Interim control 與解除條件

在方案限制解除前，CI、draft PR、雙軸 review、ready 後 squash merge 與分支清理仍按人工
流程執行；這些是可稽核的 interim controls，**不等同** GitHub 強制保護。

Issue #12 與 migration Definition of Done 的 branch-protection 條件保持未完成。解除方式只有：

1. owner 將帳號升級為支援 private repository protection 的方案；或
2. owner 另行明確決定公開 repository（目前未授權，且不能視為預設解法）。

解除後應套用 Issue #11 的 exact policy，讀回 after settings，建立一個 failing-check PR
證明 merge 被阻擋，再確認 checks 全綠且零 required reviewer 時 solo owner 可以合併。
