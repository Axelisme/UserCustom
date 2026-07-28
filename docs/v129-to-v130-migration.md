# v129 → v130 遷移指南

給 `Qubit-measure-gui` 的執行 agent。這份指南處理**收尾**，不處理轉換 —— v130 不讀舊的 branch 命名，也不讀 `Wave:` / `Role:` / `Slice:` trailer，所以沒有「把 v129 狀態轉成 v130」這回事。每條舊 branch 只有兩個結局：land 掉，或刪除。

倉庫：`/home/axel/Documents/VSCode/Python/Qubit-measure-gui`
持久分支：`feat/web_view`（使用者口述的 `feat/web_feat` 應為此分支，執行前確認）

---

## 絕對不能做的三件事

1. **不 push。** 全程只動本地。
2. **不碰非 task 的 worktree。** `.agent_state/worktrees/homo8-main` 不是 task worktree，且帶有未追蹤的 `docs/research/`，那是使用者的東西。
3. **不在任何 worktree 還有未提交修改時刪除它。** 見步驟 1。

---

## 步驟 0 — 重新驗證現況

下面的快照取自 2026-07-28，執行時必須重新確認，數字可能已變。

```bash
cd /home/axel/Documents/VSCode/Python/Qubit-measure-gui
git worktree list | wc -l
git branch --format='%(refname:short)' | grep -cE '^wave/'
git for-each-ref --format='%(refname)' | grep -c '^refs/orchestrate/'
git branch --format='%(refname:short)' | grep -E 'wave/.*/integration$'
```

對每條 integration branch 確認它是活的還是殘留：

```bash
for b in $(git branch --format='%(refname:short)' | grep -E 'wave/.*/integration$'); do
  printf "%-60s ahead=%-4s behind=%-4s %s\n" "$b" \
    "$(git rev-list --count feat/web_view..$b)" \
    "$(git rev-list --count $b..feat/web_view)" \
    "$(git log -1 --format=%ad --date=short $b)"
done
```

**判準**：`behind=0` 且最近有 commit 的是活的；`behind` 為數十且最後動作在數天前的是殘留。

2026-07-28 的結果，以及使用者確認「只有一條 valid，其餘都是舊版殘留」：

```
wave/frontend-backend-refactor-v126-device-prebind/integration
    ahead=11  behind=0   最後 07-28   ← 唯一有效的 task
wave/frontend-backend-refactor-v126-device-poll/integration
    ahead=4   behind=55  最後 07-26   ← 殘留
wave/frontend-backend-refactor-v126-night/integration
    ahead=14  behind=56  最後 07-26   ← 殘留
wave/frontend-backend-refactor-v126-recut/integration
    ahead=8   behind=56  最後 07-26   ← 殘留
wave/frontend-backend-refactor/integration
    ahead=504 behind=60  最後 07-25   ← 殘留（07-18 就分岔的舊主幹）
```

若重新驗證的結果與此不符，**停下來回報使用者**，不要按舊判斷執行。

---

## 步驟 1 — 保護未提交的工作

先找出所有帶未提交修改的 worktree：

```bash
git worktree list --porcelain | awk '/^worktree /{print $2}' | while read -r wt; do
  [ -n "$(git -C "$wt" status --porcelain 2>/dev/null)" ] && echo "DIRTY: $wt"
done
```

2026-07-28 有兩個：

| worktree | 內容 | 處置 |
|---|---|---|
| `...artifact-named-bundles-composition-correction-v120-implementation` | 4 個 `lib/zcu_tools/` 檔案的修改（`communication/attachment_host.py`、`communication/mutation.py`、`gui/.../measure_application.py`、`gui/.../artifact_bundle.py`） | **問使用者**：這些修改要保留還是丟棄。它屬於 v120 時代的殘留 branch，但改動是真的 |
| `.agent_state/worktrees/homo8-main` | 未追蹤的 `docs/research/` | **不要動**。這不是 task worktree |

對每個 dirty 的 task worktree，在得到使用者明確指示前不得刪除。要保留就先 commit 到它自己的 branch，或匯出成 patch：

```bash
git -C <worktree> diff > /tmp/<name>.patch
```

---

## 步驟 2 — Landing 唯一有效的 task

`device-prebind/integration` 的 `behind=0`，所以 `feat/web_view` 是它的祖先，可以 fast-forward，符合 S7.4「fast-forward-only」。

```bash
# 確認 ff 條件仍成立
git merge-base --is-ancestor feat/web_view \
  wave/frontend-backend-refactor-v126-device-prebind/integration \
  && echo "ff OK" || echo "已分岔，停下回報"

# 確認 integration 的樹是乾淨的
git -C <integration-worktree> status --porcelain

# landing
git checkout feat/web_view
git merge --ff-only wave/frontend-backend-refactor-v126-device-prebind/integration
```

**不 squash、不 rebase、不 cherry-pick、不建 merge commit、不 push。**

若 `ff OK` 失敗（表示期間 `feat/web_view` 又前進了），停下來回報使用者，不要自行改用 merge commit。

---

## 步驟 3 — 刪除舊版殘留

**只有在步驟 1 與步驟 2 都完成之後才執行這一步。**

### 3a. 移除 task worktree

```bash
git worktree list --porcelain | awk '/^worktree /{print $2}' \
  | grep '/.agent_state/worktrees/' \
  | grep -v 'homo8-main' \
  | while read -r wt; do
      if [ -n "$(git -C "$wt" status --porcelain 2>/dev/null)" ]; then
        echo "SKIP (dirty): $wt"; continue
      fi
      git worktree remove "$wt"
    done
git worktree prune
```

`homo8-main` 被明確排除。任何仍 dirty 的一律跳過並回報。

### 3b. 刪除舊 branch

```bash
# lane / role branch
git branch --format='%(refname:short)' \
  | grep -E '^wave/.*/(oracle|implementation)$' \
  | xargs -r -n1 git branch -D

# 殘留的 integration branch（device-prebind 已 land，此時也可刪）
git branch --format='%(refname:short)' \
  | grep -E '^wave/.*/integration$' \
  | xargs -r -n1 git branch -D

# v118/v119 時代的 legacy branch
git branch --format='%(refname:short)' | grep '^agent/'
```

最後那組 `agent/` branch 先列出來給使用者看再刪 —— 它們早於 wave 命名，可能有別的用途。

### 3c. 刪除 task refs

```bash
git for-each-ref --format='%(refname)' | grep '^refs/orchestrate/' \
  | xargs -r -n1 git update-ref -d
```

### 3d. 清理死狀態檔案

`.agent_state/` 下的這些是 S6/S7 明令禁止的「第二套 ledger」的遺留物，v130 不讀它們：

```bash
ls .agent_state/orchestrate/findings/    # per-task findings ledger
ls .agent_state/orchestrate/reviews/     # review ledger
ls .agent_state/orchestrate/*-landing.json
```

列出來給使用者確認後刪除。`.agent_state/orchestrate/version-pin.json` **不要刪**，步驟 4 要用。

`.agent_state/plans/frontend-backend-refactor/` 是 task 敘事，透過 planning-with-files 的 `archive` 歸檔，不要手動刪：

```bash
python ~/.codex/skills/planning-with-files/scripts/plan.py \
  --root . archive frontend-backend-refactor
```

若因為有未完成 phase 而拒絕，那是正確行為 —— 回報使用者，由他決定是收尾還是保留。

---

## 步驟 4 — pin migrate 到 v130

v130 的 `pin migrate` 會偵測殘留並**拒絕推進**。若它擋下來並列出清單，表示步驟 3 沒做完，回到步驟 3。

```bash
python ~/.codex/skills/orchestrate/scripts/orchestrate.py pin migrate --root .
python ~/.codex/skills/orchestrate/scripts/orchestrate.py doctor
```

`doctor` 應回報 `ok: true` 與 v130 的版本號。

---

## 步驟 5 — 開新的 integration branch

清空之後才開新 task。v130 的形狀：

```bash
orchestrate integration create --root . --task-id <新 task 名> --base <feat/web_view 的 exact SHA>
```

v130 與 v129 的差異，開始工作前要知道的：

| | v129 | v130 |
|---|---|---|
| 工作單位 | Wave（oracle + implementation 兩個 worktree） | lane（一個 worktree，內部串行） |
| branch 命名 | `wave/<task>/<wave>/<role>` | `wave/<task>/<lane-id>` |
| collect 後 | worktree 要另外手動移除 | **collect 一律自動移除 worktree** |
| Contract 保護 | `contract merge` + 跨 branch 物件比對 | 同 branch 上 `Immutable:` 宣告點與 lane tip 的 blob 比對 |
| trailer | `Wave:` `Role:` `Slice:` | `Task:` `Lane:` `Immutable:` `Origin:` `Conflicts:` |

**107 個 worktree 之所以積起來，就是因為 v129 的 collect 與 worktree remove 是兩個命令。** v130 把它們合成一個動作，這個累積路徑被堵死了。

---

## 附錄 — 2026-07-28 的完整快照

```
worktree              107（primary 之外），其中 2 個 dirty
lane/role branch      71
integration branch    5（全部未 landing）
legacy agent/ branch  2
task refs             5
pin                   v129（orchestrate_compat 129）
plans                 .agent_state/plans/frontend-backend-refactor/ + archives/
```

殘留 branch 的獨有內容（若之後發現需要救回）：

```
v126-device-poll   4 commits   device poll single-flight
v126-night        14 commits   recovery-exit-02 / -03、recovery dialog 保持開啟
v126-recut         8 commits   recovery-exit-01、recovery contract 修正
frontend-backend-refactor  504 commits，07-18 分岔的舊主幹
```

刪除前若有疑慮，這些 SHA 在 `git reflog` 裡還會留一段時間，但不要依賴它 —— 有價值的東西要在步驟 3 之前先撈出來。
