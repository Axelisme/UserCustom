---
name: planning-with-files
description: 以 explicit task-id 管理 repo-local durable task narrative；只在跨回合、critical或資訊量確有需要時使用。
user-invocable: true
skill_version: 15
---

# Planning with Files

本 skill owns **storage/schema** for one task. It stores durable narrative; Git coordination is
owned by `orchestrate`. Session and plan prose use Chinese; code and technical names stay in
English.

## Mental model: refs vs object log

- `INDEX.md` = refs: the bounded ref for current state, decisions, phase board, and pointers only.
- Stores are the object log: phase records, deferred rows, and `progress.jsonl`; phase records 在完成前可變,
  completed 後 sealed and immutable; **progress append-only**.
- Read protocol after compaction or handoff: **只讀 `INDEX.md`** first, then perform targeted
  store reads. **指標不抄本**: point to authority instead of copying live values.
- **storage/schema** is the ownership boundary; this skill does not own execution or review.

## Layout and commands

Under `.agent_state/plans/<task-id>/`, keep `INDEX.md`, `phases/NN-<slug>.md`,
`progress.jsonl`, and optional `findings.md`. `<skill-dir>/scripts/plan.py --root <repo> <cmd>`
accepts explicit task IDs: `init`, `phase-start`, `phase-set`, `log`, `status`, `checkpoint`, and
`archive`. `status` is read-only and derives live Git projection from the selected worktree.

## Schema boundary

The `phase/deferred-row/progress schema` is defined by `templates/phase.md` and the JSONL log.
A phase may mutate before completion and is sealed after `completed`; `progress` only appends.
Use the template as the authority for deferred rows instead of restating row fields here. S4/S5
references are recorded as pointers to the shared authority, not copied policy. Do not add another
ledger, status, or execution state file. The plan stores records; it does not infer runtime state
or decide close-out.

## Update boundary

Write the appropriate store at phase start/completion, decision freeze, handoff, blocker, or
verification. Keep `INDEX.md` small and pointer-based; do not copy live SHA/tree/branch values
that `status` can derive. Completed phase records and accepted deferred rows are immutable.

## Compaction and validation

`checkpoint` validates schema, required fields, and the INDEX 16 KiB budget. `archive` validates
that phases are complete and moves the plan. Template slots are allowed immediately after `init`
but active or completed phases must fill required fields. The deferred-acceptance table is 8
columns (`Slice | observable | entrypoint | steps | expected | verifier | state | accepted SHA`);
its only cross-field rule is that state `accepted` requires a full 40- or 64-hex `accepted SHA`
and every other state requires `none`. A retired 14-column table is rejected with a
migration-required error and is never auto-converted. The script is the executable authority;
this document describes only storage/schema and S4/S5 references.

## Boundary

Read/write only `.agent_state/plans/<task-id>/`. Cross-module decisions belong in their owning
artifact or ADR, not in a second plan state model.
