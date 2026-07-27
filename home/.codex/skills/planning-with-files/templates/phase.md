# Phase <NN> — <topic>

- **Status:** pending
- **Scope:** <本 phase 涵蓋什麼。>
- **Decisions made:** <引用 INDEX 的 D-ID;沒有寫 none>
- **Conclusion:** <seal 時填結論;未完成寫 pending>
- **Commit:** <seal 時填 exact SHA;沒有寫 none>
- **Evidence:** <machine and user evidence 指標;沒有寫 none>

## Deferred user acceptance

- **S6/S7:** shared admission-standard references govern acceptance and close-out.
- speculative dependency depth: validate against admission-standard S6.3.
- none — deferred rows use the table below and update in place; acceptance前 exact SHA 改變即更新該列。

| Slice | exact SHA | observable sentence | entrypoint | user steps | expected | status | Depends on | machine evidence |
|---|---|---|---|---|---|---|---|---|---|
| none | none | none | none | none | none | none (`pending_machine | reviewed_awaiting_user | accepted | rejected | stale`) | none | none |

- An accepted checkpoint freezes the exact SHA, status, and machine evidence in its row.
- A phase is sealed only when its required fields and deferred rows satisfy the shared schema.

## Notes

- <仍在 hot window、跨 session 有價值的 evidence。完成後這裡是此 phase 的完整冷紀錄。>
