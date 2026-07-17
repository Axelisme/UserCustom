---
orchestrate_compat: 70
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
the repo/risk-required broader gate with the real environment, then land, prove tree
identity, and delete the task branch. Use a worktree for one writer only when the main checkout must stay available or
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

Root may use `orchestrate lane create|cleanup`, `review checkout|cleanup`, and
`collect` pseudo aliases from the entrypoint instead. They are stateless guards around these
same operations: exact inputs only, JSON evidence, Git recheck immediately before mutation,
and Fast Fail on dirty/drifted/unabsorbed state. They never infer a verdict or queue state.
Every guard is idempotent: after an aborted turn, rerun the same command — it reports what a
prior run already applied (`recovered: already-created|already-collected|already-removed|…`)
instead of failing, so reconciliation is the rerun itself. `collect` takes
`--integration-worktree` (`--root` remains a deprecated alias) because it requires the
integration checkout, not the repository root. `orchestrate cleanup --absorbed [--dry-run]`
sweeps managed worktrees in one pass — absorbed lanes and clean detached review checkouts are
removed, everything dirty or unabsorbed is rejected per entry. `orchestrate slice status
--task-ref task/<t>` derives each lane's state read-only from Git plus receipts
(`writing|needs_fix|authorized_to_collect|absorbed`, with seam-ready and dirty flags); it
stores nothing and decides nothing — Git remains the only topology truth carrier.
`review checkout` reports the expected receipt path for its SHA so the dispatch can name it
verbatim, and `review cleanup --subject-sha <sha>` fails fast when the checkout HEAD drifted
from the reviewed SHA — drifted evidence is void.
For collect, `--authorized-sha` plus `--review-kind` with
`different-identity|focused|root-spot|mechanical` is root's **declared authorization**. The
adapter reports it but **does not infer a verdict** or claim that a formal reviewer acted.
Preferably pass `--receipt <path>` instead: the reviewer-written review receipt is validated
and its exact SHA, review kind, and profile acknowledgment are consumed directly, with no
root retranscription; only `verdict=pass` authorizes.

- Declare each writer's file scope in one sentence. A conflict means the split was poor; fix
  the plan rather than adding machinery.
- Same-file or same public interface/schema/fixture work is serial in one worktree.
- Root collects in batches: several accepted lanes in one integration pass, merged serially
  inside it. Shared foundation lands on integration first; dependent lanes start from that SHA.
- A writer may stack its next lane on **its own** announced unreviewed SHA; a later finding
  lands as a follow-up fix commit on top. Never rewrite an announced SHA that later work
  stacks on.
- **Cross-identity work bases only on a seam-ready SHA**: the commit where the writer declared
  the frozen public seam stable (`Seam-Ready: true` trailer, or the slice's terminal validated
  SHA). Working-progress SHAs are visibility, never a base for another identity — the seam may
  still move under them.
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

Landing is one squash commit with explicit user authority. Every persistence landing claims
the merge slot, even when no contention is currently visible. After the squash commit, prove
`git diff --quiet task/<task> <landed-commit>` before deleting the task branch; squash shares
no ancestry, so content identity—not ancestry—is the deletion authority.

The merge slot (`../scripts/merge_slot.py`) is an ephemeral claimant-scoped FIFO queue plus
owner-token lease, never task state. `status` is read-only; claim/renew use atomic lock
replacement. Reset `.agent_state/merge-slot/` only while quiescent: no command running and no
holder in the landing critical section. Deleting/recreating its flock file while active can
admit concurrent holders.

State-entering guards run manifest/compat preflight before lane/review creation, collection,
packet/queue publication, or merge-slot claim. Status and cleanup/recovery remain available
without a remembered session flag. This mechanizes compatibility instead of relying on root
to remember `doctor`. A task-level version pin (`orchestrate pin set|status|migrate`, a plain
JSON file under `.agent_state/orchestrate/`) makes a mid-task skill upgrade an explicit
migration at a root-chosen boundary rather than a surprise preflight failure. Profile identity is the standing orders (normalized
`developer_instructions`); retuning a profile's model or reasoning effort never fails
preflight.

```bash
merge-slot := <repo-python> "$SKILL_DIR/scripts/merge_slot.py" --root <repo>
merge-slot status
merge-slot claim <task> [--owner-token <token>] [--wait N]
merge-slot verify <task> --owner-token <token>
merge-slot renew|release|yield <task> --owner-token <token>
```

`claim` generates and returns an owner token when omitted. Preserve it only in root context;
do not write it to task_plan or logs. Only `status=acquired` authorizes entry to the critical
section. `already_acquired` and `queued` never do. Every later operation must present the
same token; a second session with the same task-id is a distinct FIFO claimant.

Keep expensive work off-slot:

1. Rebase `task/<task>` onto the persistence tip. The integration owner runs the
   repo/risk-required broader gate and records command/rationale plus exact tree. A failed
   gate followed by code changes invalidates the old evidence and requires a fresh run.
2. Claim the slot, retain the returned owner token, and proceed only on `status=acquired`.
3. Immediately before persistence mutation, run `verify <task> --owner-token <token>` and
   re-read the persistence tip.
4. Tip unchanged: squash-merge, commit, prove task/landed tree identity, then release with the
   owner token.
5. Tip moved: `yield`; never adapt the candidate inside the landing critical section. Use
   `git merge-tree --write-tree` off-slot. When conflict-free **and** new commits are
   path-disjoint, rebase, rerun the repo/risk-required broader gate on that new final tree,
   then reclaim from step 2. Otherwise restart from step 1 and resolve explicitly.

Expired holders have lost both lock and claimant-specific queue position and cannot
`verify`, `renew`, `release`, or `yield`.
