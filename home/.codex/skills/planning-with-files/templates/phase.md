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
- verifier: `user | agent`.
- state: `pending | passed | failed | blocked | accepted | superseded`.
- active rows update in place; multiple rows may share one entrypoint.
- `accepted SHA` must be a full 40- or 64-hex SHA when state is `accepted`, and `none` for
  every other state — the only cross-field rule this table enforces.

| Slice | observable | entrypoint | steps | expected | verifier | state | accepted SHA |
|---|---|---|---|---|---|---|---|
| none | none | none | none | none | none | none | none |

- A retired 14-column table is rejected with a migration-required error and is never
  auto-converted.
- A phase is sealed only when its required fields and deferred rows satisfy this schema.

## Notes

- <仍在 hot window、跨 session 有價值的 evidence。完成後這裡是此 phase 的完整冷紀錄。>
