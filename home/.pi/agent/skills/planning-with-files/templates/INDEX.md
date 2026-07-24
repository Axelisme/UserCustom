# <task-id>

**Goal:** <一段話描述本 task 要達成的具體結果。穩定,少動。>

## Current State

- <此刻已知狀態、相關 branch/worktree/位置。>
- **Next gate:** <下一個可機械驗收的動作。唯一。>

## Decisions

| ID | Status | Decision | Authority |
|---|---|---|---|
| D-001 | active | <決策與理由(一行)。> | <ADR / 被取代 decision;沒有寫 none> |

<!-- superseded 的 decision 只留一行並標 status=superseded 指向 replacement;明細不留這裡。 -->

## Phase board

| Phase | Status | Record |
|---|---|---|

## Stores

<!-- 按需讀取,永不整份載入。有 authority 來源的一律指過去,不抄本。 -->

- phases — `phases/NN-<slug>.md`,一 phase 一檔,完成即 seal
- progress — `progress.jsonl`,append-only;讀尾巴或時間區段
- findings(investigation)— `findings.md`,或 none
- evidence — task-local validation records in `progress.jsonl` or `findings.md`
- artifacts — `../../artifacts/<task-id>/`
