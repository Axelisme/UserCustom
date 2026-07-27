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
- status: `pending_machine | reviewed_awaiting_user | accepted | rejected | stale`.
- exercise result: `not_run | passed | failed | blocked`.
- active rows update in place before acceptance; multiple rows may share one exact SHA.
- `observed SHA` records where the user observation occurred. Carry-forward to a different
  candidate requires a non-`none` impact/retest basis and acceptance evidence for that candidate.

| Slice | exact SHA | observable sentence | entrypoint | user steps | expected | status | exercise result | observed SHA | Depends on | user evidence | impact/retest basis | acceptance evidence | machine evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| none | none | none | none | none | none | none | none | none | none | none | none | none | none |

- An accepted checkpoint freezes the row. Completed v13 nine-column records remain read-only;
  an active v13 row requires explicit migration to this schema.
- A phase is sealed only when its required fields and deferred rows satisfy the shared schema.

## Notes

- <仍在 hot window、跨 session 有價值的 evidence。完成後這裡是此 phase 的完整冷紀錄。>
