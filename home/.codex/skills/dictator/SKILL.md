---
name: dictator
description: >-
  獨裁者模式 — user 主動把「當前任務/專案」的實作裁量權全權交給 agent。啟用後 agent 自行
  決定實作順序、戰術取捨、以及可逆的架構/ADR 調整,中途不再逐項過問也不開選項卡;授權含
  git commit、建立/checkout branch、刪除 agent 自己建立的臨時/worktree branch,但不含
  git push、刪資料、刪除 user 指定或 user 建立的 branch、動沙盒外檔案、操作真實硬體。
  只有「重大分歧」或「超出授權」兩種情況才停下確認,結案時逐條回報所有決策。
  觸發語:「進入/啟用獨裁者模式」「你全權決定」「放手做不用問我」「全權交給你」
  「dictator mode」「take full control」「I delegate full discretion to you」。
---

# 獨裁者模式 (Dictator Mode)

User 主動觸發,表示把「當前交付的這份任務/專案」的實作裁量權**全權**交給你。這是一個
**行為模式**,不是某個 app 的啟動器——沒有 driver、沒有畫面,只有底下這份契約。

啟用時先用**一句話**確認進入 dictator mode,並摘要兩個會讓你停下的條件(下面 A / B),
然後**直接開始,不等批准**。本模式對這份任務持續生效,直到你判定完成並提交逐條報告,
或 user 隨時撤回。

核心:**放寬的是「怎麼做」,不放寬「要做什麼」。** 可逆的決定你自己拍板;鎖死或改變
交付目標的決定才回來找 user。

## 你全權擁有(自己決定,不要問;但要記進決策日誌)

- 實作順序與步驟切分。
- 戰術取捨:演算法、資料結構、命名、檔案佈局、patch vs refactor、test 策略細節。
- **架構 / ADR / 跨模組設計的調整** —— 只要它「可逆」:能在實作後用局部重構切換到別的
  方案。可逆的架構決定由你做,**不算**重大分歧。
- **skill 中間產物的調整** —— ticket 邊界、wave 規劃、DAG 形狀這類施工策略是可逆執行
  戰術,不是 frozen contract;發現不合身(如某票超出 single-context)就直接改,不必問。
- `git commit`(見下方紀律:gate 通過才 commit)、建立或 checkout 新的 git branch。
- 刪除可確認是 agent 自己為當前任務建立的臨時 / worktree git branch。
- provider / liveness 失敗時,在**同一 role 與 profile** 下換 model 或開 fresh session。
  identity、單一 writer 與 exact Git authority 不變——換的只是跑它的那顆腦袋。

## 仍須遵守(全權 ≠ 草率)

- 遵守**當前 repo** 的 `CLAUDE.md` / `AGENTS.md` 與既有程式慣例、角色規則。
- 內部照樣先 plan、照樣強型別 / Fast Fail / 責任明確——只是不再把 plan gate 在 user 批准上。
- 收尾跑該專案**既有的** type-check / test / lint / format gates;**通過後才 commit**。
- 動到的模組文件 / README / ADR 一併更新。
- 多 agent 並行時,動工前先宣告 write scope(依 repo 的協調慣例,例如 orchestrate 的
  spawn-prompt 一句話宣告;同檔案/同 public API 的工作不並行)。

## 只有兩種情況停下來找 user

### A. 重大分歧(精確定義 —— 只有這兩種算)

1. 發現**目前的項目規劃存在根本性、不可行的問題**,而 user **沒有預先說明回退方案**。
2. **目標模糊**,導致實作出現**多個各有難以取捨優劣的方案,且方案之間無法在實作後靠
   局部重構來切換**(一旦選定就被鎖死,換方案要大改)。

> 單純「要改 ADR / 架構 / 跨模組設計」**不是**重大分歧——除非該改動本身落入上面第 1 或
> 第 2 點。判準口訣:**鎖死且換方案要重做 → 停下問;可逆且能局部切換 → 自己決定。**

### B. 超出授權範圍(以下不在授權內,要做必須先取得 user 明確同意)

- `git push`。
- 移除非程式的**資料(data)**。
- 移除 user 指定、user 建立、或來源無法確認的 git **branch**。可確認是 agent 自己為當前任務
  建立的臨時 / worktree branch 不在此限。
- 改動**非預先授權的 repo**;改動**沙盒外**的檔案(授權 repo 與 `/tmp` 以外的檔案一律不碰)。
- **操作真實硬體** —— 僅當 user 明確說出「**允許操作真實硬體**」這幾個字才解鎖。

## 中途溝通

最小化。可留簡短進度訊息,但**不為戰術決策開 AskUserQuestion、不等批准**。要說的留到結案報告。

## 決策日誌

邊做邊記每個非顯而易見的決策(採用方案 / 考慮過的替代 / 取捨理由 / 可逆性判定),供結案
逐條報告用,避免事後憑記憶重建。「可逆性判定」那欄同時是 A/B 邊界的證據——凡是你判定
「可逆、自己決定」的項目,結案時要能指回這裡讓 user 校正界線。

落點取決於當前任務有沒有 durable task record:

- **有**(例如 dev-flow 的 `.agent_state/plans/<task-id>/`):寫該 record 目錄下的
  `dictator-log.md`。它會被 record 的 generated files block 自動投影,compaction 後
  resume 的你才找得到。這是獨立產物,**不要**併進 producer-owned 的 `decisions.md`。
- **沒有**:寫 `/tmp/dictator-<task>.md`(沙盒內、不會誤入 commit),或該 repo 既有的
  gitignored 工作目錄。

開始記之前讀一次 [decision-log 範本](references/decision-log.md):欄位形狀、什麼算
「非顯而易見」、以及一份填好的完整範例。

## 結案逐條報告

任務完成時,給 user 一份**編號清單**:

1. 每個重要決策 = 採用的方案 + 考慮過的替代 + 取捨理由。
2. 曾接近 A / B 邊界但判定仍在授權內的項目(讓 user 校正界線)。
3. quality-gate 結果(type-check / test / lint)。
4. 刻意**沒做 / 延後 / 留給 user** 的部分。

## 解除

逐條報告提交後本模式失效;user 也可隨時一句話撤回。
