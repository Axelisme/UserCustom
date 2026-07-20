# <task-id> 任務計劃

**Last updated:** YYYY-MM-DD

## Goal

<用一段話描述本 task 要達成的具體結果。>

## Current State

- <目前已知狀態。>
- <相關 branch / worktree / 文件位置。>

## Architecture Baseline

- <相關模組、ADR、README 或設計約束。>
- <如果本 task 不涉及架構，寫明不涉及。>

## Active Domain Packets

### <domain>

- Domain: <domain id / bounded responsibility>
- Owner / Reviewer: <domain owner / independent reviewer；沒有則寫 none>
- Current SHA: <full SHA snapshot（寫下時為準，會過時；現況一律以 Git 為準）；尚未形成則寫 none>
- Frozen decisions: <目前生效的決策>
- Superseded decisions: <已被取代的決策；沒有則寫 none>
- Open stop conditions: <仍會停止工作的條件；沒有則寫 none>
- Review debt: <不在此手抄；由 `findings status` / `wave status` 導出>
- Finding ledger: <不在此手抄；由 `findings status` 導出（ledger 才是真相）>
- Anomalies: <unusable-evidence 指令與替代證據；沒有則寫 none>
- Source map: <artifact path；沒有則寫 none>
- Next acceptance gate: <下一個可機械驗收的 gate>

## Phase Status

| Phase | Status | Scope | Acceptance |
|---|---|---|---|
| Phase 1 | pending | <範圍> | <驗收條件> |

## Decisions

| ID | Status | Decision | Supersedes / Authority |
|---|---|---|---|
| D-001 | active | <決策與理由。> | <被取代decision或ADR；沒有則寫none> |

## Errors Encountered

| Error | Attempt | Resolution |
|---|---|---|

## Historical Phase Summary

| Phase | Topic | Conclusion / Commit |
|---|---|---|

## Active Notes

### Phase 1 — <topic>

- Conclusion / Commit: <完成時填入結論與 exact commit；未完成時寫 pending>
- Detail: <仍在 hot window 內、跨 session 有價值的 evidence。>
