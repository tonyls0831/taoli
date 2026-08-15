# Repository governance

最後驗證：2026-08-15

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

## Visibility 決策

Repository owner 於 2026-08-15 明確授權將 `tonyls0831/taoli` 由 private 改為 public，
以便在 GitHub Free 套用已核准的 `main` protection policy。變更後由 GitHub API 讀回
`visibility = public` 與 `private = false`。這項授權只涵蓋 repository visibility 與既定
migration 工作，不授權通知、排程、券商連線或交易自動化。

Repository 公開代表程式碼、完整 Git history、Issues 與 pull requests 可由任何人讀取；
公開前的 tracked tree 與完整 reachable history 已依 Issue #13 完成不輸出值的 secret audit，
結論與重建驗證見 `docs/security-and-reproducibility-audit.md`。

## Before／after settings evidence

### Before：2026-08-13

變更前以 GitHub REST API 確認 repository 為 private；squash、merge commit、rebase merge
皆允許，`delete_branch_on_merge` 為 false。讀取 `main` branch protection 與 repository
rulesets 均回傳 HTTP 403：目前帳號方案須升級 GitHub Pro，或把 repository 改為 public，
才能在 private repository 使用這兩項功能。因此本次無法建立 protection/ruleset，
也沒有可聲稱為「failed checks 確實阻擋 merge」的 after evidence。

GitHub 官方文件同樣說明：GitHub Free 可在 public repository 使用 protected branches／
rulesets；private repository 需要 GitHub Pro、Team 或 Enterprise。參考：

- <https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches>
- <https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets>

### After：2026-08-15

Repository 公開後，讀取 protection endpoint 由方案限制的 HTTP 403 轉為「尚未保護」的
HTTP 404，rulesets endpoint 可正常讀取且為空。接著以 branch-protection endpoint 套用並
讀回以下設定：

- required status checks：`Python 3.10`、`Python 3.14`，`strict = true`；
- require pull request before merging，required approving reviews = 0；
- `enforce_admins = true`，owner／administrator 不得繞過 required PR 或 checks；
- `allow_force_pushes = false`、`allow_deletions = false`；
- push restrictions 為空；linear history、code-owner review、conversation resolution、
  branch lock 等未核准的額外規則均未啟用。

### Failing-check 阻擋證據

暫時 PR #28（head `eeaea40fbc6890f6337cc6d2cb6bd73e53287670`）只加入一個
刻意失敗的 unittest。將 PR 標記為 ready（`isDraft = false`）後，GitHub Actions run
`31893638822` 中 `Python 3.10` 與 `Python 3.14` 都為 failure；此時 GitHub 回報
`mergeStateStatus = BLOCKED`，因此 draft 狀態不是阻擋原因。本驗證沒有呼叫 merge；
PR #28 隨後以 unmerged 狀態關閉，專用遠端分支也已刪除。

Solo-owner merge 則以本文件的正常治理 PR 驗證：required checks 與 Standards + Spec review
全數通過、required approving reviews 維持 0 後，由 owner 使用正常 squash merge；最終 PR、
commit 與 CI run 證據會記錄於 Issue #12。這是 policy 允許的正常 merge，不是 bypass。
