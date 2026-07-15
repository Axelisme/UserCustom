---
orchestrate_compat: 53
---

# Git coordination and landing

Read this reference before creating or changing task/lane branches, using worktrees,
collecting or deleting lanes, or landing on a persistence branch. The hard rules in
`../SKILL.md` remain authoritative.

## Terms and branch hierarchy

- **Main checkout** = the repo-root working directory — a *place*, not a branch. It normally
  stays on the user's feature branch and is the only place with the full environment (for
  example the repo's `.venv`); every gate needing that environment runs here.
- **Persistence branches** = `main` and user feature branches. Their history is immutable.
- Branch hierarchy: persistence ← `task/<task>` (integration, exactly one per task) ←
  `agent/<task>/<lane>` (zero or more lanes, one writer each). Everything below persistence
  is orchestrator-owned and mutable, but rewrite integration history only between waves and
  never under a lane based on the rewritten range. Rework invalidates review of the old SHA.

## Single writer

Single-writer code changes work directly on the task branch with no lane and normally no
worktree: create `task/<task>` in the main checkout, implement, run targeted acceptance and
the repo/risk-required broader gate with the real environment, then land and delete the task
branch. Use a worktree for one writer only when the main checkout must stay available or
user-owned dirty state would conflict. Q&A, read-only research, and one-round review create
no branch.

## Multi-writer parallelism

Multiple writers require multiple worktrees, with one writer per worktree at a time:

```bash
git branch "task/<task>" <base>
git worktree add ".agent_state/worktrees/<task>-<lane>" \
  -b "agent/<task>/<lane>" "task/<task>"
# spawn one writer per worktree with an explicit file scope
# root collects serially inside the integration worktree
git merge --no-ff "agent/<task>/<lane>"
git worktree remove ".agent_state/worktrees/<task>-<lane>"
```

- Declare each writer's file scope in one sentence. A conflict means the split was poor; fix
  the plan rather than adding machinery.
- Same-file or same public interface/schema/fixture work is serial in one worktree.
- Root merges serially. Shared foundation lands on integration first; dependent lanes start
  from that SHA.
- Never copy, create, or repair environments (`.venv`, `node_modules`, caches) in worktrees.
  Point the main checkout's toolchain at worktree sources; for Python, a common shape is
  `PYTHONPATH=<worktree>/<pkg-root> <main>/.venv/bin/python -m pytest ...`. Follow repo docs
  when they specify another recipe. Full-environment gates run in the main checkout.
- Resolve a merge conflict by recovering each side's intent from commits and the plan;
  preserve compatible intent, choose according to the frozen goal where incompatible, and
  record the trade-off. Conflict resolution never invents new behavior.
- Before deleting a collected lane branch, prove absorption with
  `git merge-base --is-ancestor <lane> <task>` or tree identity via
  `git diff --quiet <lane> <task>`. `git branch -D` is allowed only after that evidence.

## Landing on persistence

Landing is one squash commit with explicit user authority. After landing, delete the task
branch and remaining lanes; squash shares no ancestry with integration, so the task branch
has no further purpose.

Multi-task contention uses the merge slot (`../scripts/merge_slot.py`), an ephemeral lock +
FIFO queue and never task state. Reset `.agent_state/merge-slot/` only while quiescent: no
command running and no holder in the landing critical section. Deleting/recreating its flock
file while active can admit concurrent holders.

```bash
<repo-python> "$SKILL_DIR/scripts/merge_slot.py" --root <repo> \
  status | claim <task> [--wait N] | renew <task> | release <task> | yield <task>
```

Keep expensive work off-slot:

1. Rebase `task/<task>` onto the persistence tip, run the repo/risk-required broader gate
   once, record the command/rationale and that tip.
2. Claim the slot and re-read the persistence tip.
3. Tip unchanged: squash-merge and release.
4. Tip moved: use `git merge-tree --write-tree`. Only when conflict-free **and** new commits
   are path-disjoint from this task may root rebase in place, run thin checks, merge, and
   release (`renew` if needed). Otherwise `yield` and restart from step 1.

Expired holders have lost both lock and queue position and cannot `renew` or `yield`.
