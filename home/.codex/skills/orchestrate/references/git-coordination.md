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
identity, and delete the task branch. Use a worktree for one writer only when the main
checkout must stay available or user-owned dirty state would conflict.

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

Root may use the `orchestrate` pseudo aliases from the entrypoint instead. They are
stateless idempotent guards around these same operations: exact inputs only, JSON evidence,
Git recheck immediately before mutation, Fast Fail on dirty/drifted/unabsorbed state, and
after an aborted turn the rerun itself is the reconciliation — it reports what a prior run
already applied (`recovered: already-created|already-collected|already-removed|…`). The one
deliberate exception is spool-item removal (`queue remove`): item absence alone cannot
distinguish already-removed from never-existed, so its rerun fails and the consumer
reconciles by evidence comparison instead ([File transports](transports.md)). They
never infer a verdict or queue state; Git remains the only topology truth carrier.

- `lane create` — lane branch plus worktree at an exact base.
- `review checkout` — detached exact-SHA review worktree; it reports the expected receipt
  path so the dispatch can name it verbatim.
- `review verdict --receipt <path> [--subject-sha <sha>]` — validates and routes a receipt
  without judging it: `pass` reports the exact collect authorization, `needs_fix` returns
  findings to the original writer, `blocked|needs_decision` returns to root, and an invalid
  or wrong-subject receipt is reported as unusable evidence.
- `collect --integration-worktree <path>` (`--root` is a deprecated alias; it requires the
  integration checkout, not the repository root) merges one authorized exact lane SHA.
  Preferably pass `--receipt <path>`: the reviewer-written receipt's exact SHA, review kind,
  and profile acknowledgment are consumed directly, with no root retranscription, and only
  `verdict=pass` authorizes. `--authorized-sha` plus `--review-kind`
  `different-identity|focused|root-spot|mechanical` is root's **declared authorization** —
  reported, never inflated into a verdict. `--scope <manifest>` fails on out-of-scope writes.
- `cleanup --absorbed [--dry-run]` — one-pass sweep: absorbed lanes and clean detached
  review checkouts are removed, everything else rejected per entry with a reason.
  `cleanup --worktree <path> [--subject-sha <sha>]` removes exactly one target with the
  same proofs — absorption for a lane, clean checkout for a review, and `--subject-sha`
  fails fast on a drifted review HEAD (drifted evidence is void).
- `slice status --task-ref task/<t>` — read-only derivation of each lane's state from Git
  plus receipts (`writing|needs_fix|authorized_to_collect|absorbed`, seam-ready and dirty
  flags, cross-lane write-set overlap); it stores nothing and decides nothing.

- Declare each writer's file scope in one sentence, or as a hand-written scope manifest JSON
  (`owned_paths`/`excluded_paths`/`shared_read_only_paths`) checked by `scope check` and
  `collect --scope`. A conflict still means the split was poor; fix the plan rather than
  adding machinery.
- A writer who must grow its scope (a missing test, a shared fixture) proposes
  `scope amend --manifest <cur> --add-owned <pattern> --reason <why> --output <new>`: a new
  manifest file carrying the amendment lineage (previous manifest SHA-256, patterns, reason).
  Root approves by adopting the amended manifest in `scope check`/`collect --scope`;
  excluded patterns are never amendable — an exclusion override needs a fresh root manifest.
- Same-file or same public interface/schema/fixture work is serial in one worktree.
- Shared foundation lands on integration first; dependent lanes start from that SHA.
- Never rewrite an announced SHA that later work stacks on; a finding lands as a follow-up
  fix commit on top.
- **Cross-identity work bases only on a seam-ready SHA**: the commit where the writer declared
  the frozen public seam stable (`Seam-Ready: true` trailer, or the slice's terminal validated
  SHA). Working-progress SHAs are visibility, never a base for another identity — the seam may
  still move under them.
- Never copy, create, or repair environments (`.venv`, `node_modules`, caches) in worktrees.
  Point the main checkout's toolchain at worktree sources; for Python, a common shape is
  `PYTHONPATH=<worktree>/<pkg-root> <main>/.venv/bin/python -m pytest ...`. For uv projects,
  `UV_PROJECT_ENVIRONMENT=<main>/.venv uv run --no-sync ...` reuses the main environment
  read-only; a plain `uv run` in a worktree builds a fresh `.venv` and re-resolves Git
  dependencies — network and cache drift a lane must not depend on. Follow repo docs when
  they specify another recipe. Full-environment gates run in the main checkout.
- Resolve a merge conflict by recovering each side's intent from commits and the plan;
  preserve compatible intent, choose according to the frozen goal where incompatible, and
  record the trade-off. Conflict resolution never invents new behavior.
- Before deleting a collected lane branch, prove absorption with
  `git merge-base --is-ancestor <lane> <task>` or tree identity via
  `git diff --quiet <lane> <task>`. `git branch -D` is allowed only after that evidence.

## Landing on persistence

Landing is one squash commit with explicit user authority, serialized by the built-in
landing lock `land finish` takes itself. After the squash commit, prove
`git diff --quiet task/<task> <landed-commit>` before deleting the task branch; squash shares
no ancestry, so content identity—not ancestry—is the deletion authority.

Declare the **landing policy** at contract freeze in a hand-written landing declaration JSON
(`{landing_version: 1, task_id, policy, target_ref}`): `validate-only` (the task ends at a
validated task branch), `land-with-confirmation` (finish needs one explicit user
confirmation), `commit-authorized` (land locally), or `publish-authorized` (land plus push).
The declaration carries the user's landing authority for step 7; the close never stalls at
"validated but unlanded".

`land status --root <checkout> --task-ref task/<t> --declaration <path> [--gate-receipt <p>]`
reports the finish chain read-only — final gate, landing authority, squash landing, tree
identity, lane cleanup — and names the first missing step. `land finish` adds `--task-sha`
(exact), a **passed** gate receipt bound to that SHA, and `--confirmed` under
land-with-confirmation; it Fast Fails on staged changes or user-owned dirty paths that
overlap the landing diff, then takes the non-blocking landing lock, re-reads the target tip
under it, squash-merges, commits, proves task/landed tree identity, and reports the
remaining cleanup — plus the push, under publish-authorized — as next steps. If the tip
moved since the gate, rebase and rerun the gate on the new tree before retrying; never adapt
the candidate inside the locked section. Both commands are aliases over the sequence below
and the git commands stay valid on their own.

Keep expensive work off-lock: rebase `task/<task>` onto the persistence tip first, run the
repo/risk-required broader gate there, and record command/rationale plus exact tree — a
failed gate followed by code changes invalidates the old evidence and requires a fresh run.

**Concurrent roots** landing on the same repo are the only trigger for the external
merge-slot protocol (`../scripts/merge_slot.py`): a claimant-scoped FIFO queue plus
owner-token lease (`status|claim|verify|renew|release|yield`). Only `status=acquired`
authorizes entry; keep the token in root context only; a holder that expired can no longer
`verify|renew|release|yield`. Pass `--merge-slot-held` to `land finish` to record the claim.
Reset `.agent_state/merge-slot/` only while quiescent.

State-entering guards run manifest preflight before lane/review creation, collection,
packet/queue publication, or landing; status and cleanup/recovery stay available without
one. The guards also check the task-level version pin
(`orchestrate pin set|status|migrate`, a plain JSON file under `.agent_state/orchestrate/`);
adoption mechanics live in [Delegation and review](delegation-and-review.md). Profile
identity is the standing orders (normalized `developer_instructions`); retuning a profile's
model or reasoning effort never fails preflight.
