# Phase <NN> — <topic>

- **Status:** pending
- **Scope:** <本 phase 涵蓋什麼。>
- **Decisions made:** <引用 INDEX 的 D-ID;沒有寫 none>
- **Conclusion:** <seal 時填 final landing + cleanup 結論;未完成寫 pending>
- **Commit:** <seal 時填 exact final landed SHA;沒有寫 none>
- **Evidence:** <final landing / cleanup evidence 指標;沒有寫 none>

## Deferred user acceptance

- **speculative dependency depth:** derive from the pending dependency edges; hard max 10.
- none — Night Mode 延後 S5 時，改用下表並 update-in-place；acceptance 前 exact SHA 改變即更新該列。

| Slice | exact SHA | observable sentence | entrypoint | user steps | expected | status | Depends on | machine evidence |
|---|---|---|---|---|---|---|---|---|
| none | none | none | none | none | none | none (`pending_machine | reviewed_awaiting_user | accepted | rejected | stale`) | none | none |

- An accepted checkpoint does not mean landed; the accepted row is frozen as exact SHA, status, and machine evidence.
- Partial landing stays in `progress.jsonl`; it leaves the phase open and performs no cleanup or archive.
- Completion requires final landing and cleanup evidence; `Commit` is the final landed SHA.

## Notes

- <仍在 hot window、跨 session 有價值的 evidence。完成後這裡是此 phase 的完整冷紀錄。>
