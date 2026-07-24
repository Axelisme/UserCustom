# skill_feedback2：runtime-pi / pi-subagents pipeline 實作回饋

## 完成項目

1. `runtime-pi.md` 已加入互動式 Root flow：不要為了等 role pipeline 完成而呼叫 `subagent_wait` / `wait_subagent`；若沒有可並行的本地工作，直接結束 turn，等 Pi 的 subagent completion notification 喚醒；若在 active goal mode 且有 `yield_goal`，用具名 reason yield pending role/pipeline completion。
2. `pi-subagents` 已把 pipeline 宣告與 task enqueue 分開：`pipeline.attach` 現在只用 `name` 宣告空 pipeline；`enqueue` 才新增 pending tasks；unanchored pipeline 保持 idle+pending，不會假裝 launch。
3. 已同步修正 runtime/tool description 與測試；UserCustom orchestrate mirrors / manifests 也已更新並通過 doctor。

## 驗證證據

- UserCustom：`python -m unittest discover tests` → 122 tests OK。
- UserCustom：Codex/Pi orchestrate doctors → `ok: true`。
- UserCustom：`home/.codex/skills/orchestrate/runtime-pi.md` 與 `home/.pi/agent/skills/orchestrate/runtime-pi.md` byte-identical。
- pi-subagents：`npm test` → 1354 passed。
- pi-subagents：`npm run test:integration` → 654 passed, 2 skipped。
- pi-subagents：`npm run test:e2e` → 4 passed。
- Fresh review：runtime-pi change pass；pipeline change first review found one blocker, fixed後 re-review pass。

## Orchestrate 流程觀察

- 最新 dev-flow 的 proportional fix 有用：review 發現 `release` 對 unanchored pending pipeline 會轉 held 的小缺陷後，沒有重跑整個 Oracle ceremony，直接讓單一 Implementer 做局部修正，速度比舊流程好很多。
- Oracle 首輪 Contract 仍過度保守且不夠精準：它把「attach 宣告空 pipeline」寫成「unanchored enqueue 永遠 idle」，但沒有先明確處理舊 source-attach lifecycle tests 的去留，導致 Implementation 被迫 checkpoint blocked。後續 Contract correction 才收斂。
- Reviewer 的價值主要在 diff-level 行為洞察：自動測試通過後仍抓到 hold/release 邊界，這類 focused review 值得保留，但不需要重新打開雙角色大循環。

## 建議

1. **pipeline contract 要補一個明確 ADR/usage envelope**：現在 `attach` 不再建立 continuation anchor，`enqueue` 對 unanchored pipeline 只 durable queue；若未來要讓 empty pipeline 自行 dispatch 第一個 task，需要新增 explicit agent/launch authority，不要偷偷復活舊 `runId` attach 語意。
2. **保留 source-anchored successor code 的狀態要決策**：目前部分 anchored successor code 仍存在，但 public tests 已改成 declaration-only surface；建議後續獨立任務決定要刪除 dead path，或重新以新 action（例如 explicit `adopt` / `bind-anchor`）暴露。
3. **orchestrate Runtime Pi 文件可再加一個微型 example**：現在文字已足夠測試，但未來可在不增肥的前提下放一行 example reason：`yield_goal({ reason: "Waiting for wave-oracle pipeline completion notification." })`。
4. **Contract correction 應要求 Oracle 主動列 legacy assertions disposition**：當 user 改變 public semantics 時，Oracle 不只新增 tests，還要列出舊 tests 是 preserved / rewritten / deleted，避免 Implementation 才發現互斥。
