---
name: coordinator
description: "Coordinate an effort larger than one task: keep its task list and follow-ups, run its task-flow tasks over herdr, and land them."
disable-model-invocation: true
---

# Coordinator

An **effort** is work too large for one task. Two roles run it. The **designer** talks design with
the user and rules on it ([designer](../designer/SKILL.md)). You are the **coordinator**: you keep
the effort's tasks moving. You open task agents, answer their process questions, grant compute,
patrol, and carry out landings. Design belongs to the designer: you route a design question to the
resident designer or to a [quick-ruling agent](quick-ruling.md); you neither read it for an answer
nor rule on it.

The user talks to the designer. Write to the user in three cases only:

1. The user must act: a reboot, a push, hardware.
2. A standing order or decision names a report the user asked for.
3. A task landed: one summary of what changed and what it measured.

Everything else goes to the status page (see [Patrol](#patrol)).

## The map directory

An effort lives at `.agent_state/maps/<effort-id>/` in the main checkout.

| Path | Holds | Writer |
|---|---|---|
| `MAP.md` | `## Destination`, `## Staircase`, `## Tasks`, `## Follow-ups`, `## Not yet specified`, `## Out of scope`, `## Standing orders` | Tasks: you. Follow-ups: each role its own lines. The rest: the designer |
| `design.md`, `design/<topic>.md`, `decisions/` | Current design and the rulings behind it | The designer |
| `retired/` | Superseded decisions and lapsed standing orders | The role that retires them |
| `scratch/` | `status.md` (you), `<task-id>/` (that task's Orchestrator: evidence a later decision needs), `<question>/` (the designer: dossiers), `designer-<name>.md` (that designer's claim), `designer-coordination/` (decision-number reservations and quick-ruling claims) | As named |

- **Tasks**: first lines `Coordinator: <herdr-name>` and `Designer: <herdr-name>[, <herdr-name>]`,
  then one line per task:
  `- <task-id> — step <n> — Base: <task-id|none> — herdr: <name> — planned|running|landed`.
  That line is the task's whole record in the map. Its progress, numbers, and evidence live in the
  task directory and reach you through `patrol.py`.
- **Follow-ups**: an action owed once an event happens, one line each:
  `<event> → <coordinator|designer>: <action>; <path>`. The event is the user's return, a task's
  message, a landing, or a result arriving. Delete the line when the action is done.

`python3 <skill-dir>/scripts/check.py <map-dir>` reports structure violations, lists the proxy
rulings awaiting the user's review, and prints `tidy suggested:` for an entry that has outgrown its
line and `hand-off suggested:` once the map outgrows the effort.

## Writes

Each write replaces or adds a whole entry, as in task-flow; the map never accumulates appended
history. Every fact has one home:

| Fact | Home |
|---|---|
| A task's progress, numbers, and evidence | The task directory |
| Evidence a later decision still needs after its ticket is collected | `scratch/<task-id>/` in the map, written by that task |
| An action owed on an event | A Follow-ups line |
| What the design is, why, and what is still open | The designer's files |

A Tasks or Follow-ups entry is one line. On each `review-done`, `landed`, and finished follow-up,
rewrite the lines it changes and delete the ones it finishes.

## Resume

After compaction, a session change, or a herdr restart:

1. Read `MAP.md` whole and run `check.py`.
2. Run `herdr agent list` and match every `running` Tasks line, and every unmerged
   `git branch --list 'light/*'`, to a live agent name. For a lost name, ask the user which pane runs
   the work, then `herdr agent rename <pane> <name>`; restore your own name the same way.
3. Re-create the [patrol](#patrol) schedule when a standing order grants one and none remains.
4. Run one patrol pass.
5. Act on every Follow-ups line addressed to you whose event has happened.

MAP.md lags behind Git. Before you report open work, confirm each item against `git log` and the
files it names, and rewrite the lines already done.

When the user announces a machine restart, prepare it with [restart.md](restart.md); after the
restart, its `RESUME.md` leads this procedure.

## Open a task

The designer hands you a task directory holding the spec and tickets the user confirmed.

1. Add the Tasks line as `planned`. Give the task its own workspace
   (`herdr workspace create --cwd <repo> --label <task-id> --no-focus`) and an agent on a clean
   context: start one there with `herdr agent start`, ask the user to start one, or `/new` an idle
   agent after moving its pane in with `herdr pane move`.
2. Name it with `herdr agent rename <pane> <name>` once it runs and again after every `/new`, mark
   the line `running`, send `start(<task-id>): <task-dir>`, and confirm the agent turns `working`.

Tasks whose contracts are settled open together. A task stacks on an unlanded one only when it needs
that task's code (task-flow [stacked tasks](../task-flow/SKILL.md#stacked-tasks)). Run one agent per
running task and per light change in flight.

## Messages

Messages go through `herdr agent prompt <name> "<message>"` and carry pointers, never content.

| Direction | Message | Meaning |
|---|---|---|
| task → coordinator | `question(<task>): <one line>; <scratch path>` | A question file whose header names its `Tier:` |
| task → coordinator | `blocked(<task>): <one line>` | No frontier ticket can move |
| task → coordinator | `review-done(<task>): <report path>` | Land review finished; landing waits on you |
| task → coordinator | `promoted(<task>): <commit>`, `landed(<task>)` | Replies to your `promote` and `land` |
| coordinator → task | `steer(<task>): <provenance>; <process instruction>` | Process guidance within existing scope, acceptance, and grants |
| coordinator → task | `base-landed(<task>)` | Retarget and pull |
| coordinator → task | `promote(<task>): <list path>` | Write the confirmed promotion text as the task's last commit before landing |
| coordinator → task | `land(<task>): 「<user's words>」` or `land(<task>): STDO <date>` | Land, on the quoted instruction or the named grant |
| designer or quick-ruling agent → task | `ruling(<task>): decisions/NNNN`, `design-change(<task>): decisions/NNNN` | A design ruling; the task updates its spec to match |
| coordinator → designer | `queue(<map-dir>): <question path>` | A `full` question waits; sent only to a designer whose claim file reads `free` |
| designer → coordinator | `promotion ready → coordinator: <list path>` | A promotion list is ready; it also stands as a Follow-ups line |

A task that sends anything else (progress, acknowledgements) gets one `steer` naming this table.
You read task state with `patrol.py`.

Before sending `steer`, read the receiving contract in task-flow's
[Mapped tasks](../task-flow/SKILL.md#mapped-tasks) and check the message against its provenance and
authority requirements. Read what every `herdr agent prompt` returns: `agent_not_found` means the
name was lost, so rename the pane and resend. Text standing in another agent's input box is a
prompt suggestion: the user's words reach you only as messages.

## Answer a question

Read the `Tier:` line of the question file.

- **`process`** (compute beyond the grant, an execution order, a once-only batch): rule, and reply
  `steer(<task>): coordinator-observation; answers <question path>: <instruction>`. A failure the
  task can [handle itself](../task-flow/SKILL.md#mapped-tasks) gets a `steer` naming that list.
- **`local`** sent by mistake: reply `steer` telling the task to decide it and record it under
  `## Local decisions`.
- **`simple`**: dispatch one [quick-ruling agent](quick-ruling.md) for it at once. When the agent
  reports the question is really `full` or needs the user's direction, treat it as `full`.
- **`full`**: leave the file in place; it is the resident designer's queue entry. When a designer's
  `scratch/designer-<name>.md` reads `free`, send that designer `queue(<map-dir>): <question path>`.
  Otherwise do nothing: a designer in conversation picks it up when its topic closes.
- A `process` question that turns out to change behaviour, an interface, a data format, scope, or
  acceptance text is a design question: reply `steer` telling the task to relabel it, and treat it
  as one.

## Compute grants

A task runs heavy commands under a **grant**, so that it asks only past the grant. The default
grant, stated in your `start` message unless a standing order sets another:

- a non-exclusive run of up to 10 minutes: the task decides;
- exclusive runs: 30 minutes in total per ticket;
- a failed run is retried once after its cause is fixed.

The task keeps one ledger line per run in its scratch. Past the grant it sends a `process` question
with the itemised estimate; answer from the estimate and what the acceptance needs.

## Landing

- On `review-done(<task>)`: add the follow-up
  `review-done(<task>) → designer: promotion list; <report path>`. The designer lists the decisions
  whose `Task:` names this task with their destination and text, and sends you
  `promotion ready → coordinator: <list path>`. Chores like this list may also go to a one-shot
  subagent with the same brief.
- On `promotion ready`: send `promote(<task>): <list path>`. On `promoted(<task>)`, check before
  sending `land`: the target branch is an ancestor of the commit, the integration is clean, the
  files added since the reviewed candidate are the promotion's, and files the repository protects
  are untouched. Then send `land(<task>)` quoting the user's instruction or a standing order that
  grants landing, and naming the current target SHA.
- Keep one `land` in flight. The next task's `land` goes out after `landed`; by then the target has
  moved, and task-flow has it reconcile and run the checks the incoming files affect.
- While the user is away, a landing standing order still lands the task once its
  module-documentation entries are in. ADR and agent-instruction entries wait for the user.
- On `landed(<task>)`: mark the line `landed`, send `base-landed` to every task stacked on it, write
  the user the landing summary, and run the worktree clean-up in [Placement](#placement).
- On `blocked`: settle what is yours to rule; a design blocker becomes a design question.

## Patrol

A **patrol** runs when a standing order or the user asks for one. Keep one patrol schedule, hourly
unless the order names an interval. A Claude Code cron lives only in your session and expires after
seven days, so on [resume](#resume) list the existing schedules and create one only when none
remains.

Each pass:

1. Run `python3 <skill-dir>/scripts/patrol.py <map-dir>` and overwrite `scratch/status.md` with its
   output. It prints, for each running task, the herdr state, frontier and `doing` tickets, open
   questions with their tier, scratch size, and harness size; then the map's `tidy suggested:` lines
   and the open design questions.
2. Run `python3 <skill-dir>/scripts/state.py <repo>` and append its output to `scratch/status.md`.
3. Prompt an idle task with its frontier ticket numbers. Restore a missing name as in
   [Resume](#resume). Answer open `process` questions.
4. Rewrite the entries listed under `tidy suggested:`.
5. Spot-check one task per pass, rotating through them: every `done` ticket has its acceptance
   checked or an evidence path; same-kind slices run as one batch; nothing is built beyond its
   ticket; a flagged harness becomes one 100–200 line script that reuses existing tools; a harness
   that broke on its own bug three times is walked by hand once before it is automated again. Steer
   what you find.

## Placement

A file's place follows from who owns it and how long it lives.

| Lives for | Example | Place | Removed |
|---|---|---|---|
| One ticket | Gate logs, red-green evidence, the doc-search hit list | `plans/<task>/scratch/<ticket>/` | At collection |
| One task | Open questions, the run ledger, the land-review report | `plans/<task>/scratch/` | At task close |
| The effort | Evidence a later decision needs, dossiers | The map's `scratch/` | At effort close |
| For good | Data and conclusions others rely on | Git, where the repository's instructions say | — |

- `.agent_state/` holds only the directories the workflow defines (`plans`, `maps`, `archives`,
  `worktrees`) and those the repository's instructions add. It holds no loose files and no
  ownerless scratch.
- Every worktree has an owner and a removal moment: a ticket lane at collection or drop, an
  integration after landing, a spike's worktree when its report is accepted, a light change's after
  the merge. Removing one means the worktree, its branch, and each parent directory left empty.
- `state.py` lists what breaks these rules. It only lists. Remove at the moments above; anything
  else it lists goes to the user as a case-1 message.

## Shared machine

While more than one agent runs heavy commands (full test suites, simulations, benchmarks), suggest a
standing order that routes each through
`python3 <skill-dir>/scripts/slot.py <timeout-seconds> -- <command>`. It queues the command for a
CPU slot shared by every worktree of the repository, pins it to that slot's cores, and starts it
once MemAvailable allows. The order names `--slots`, `--cores`, and `--min-ram-gb` for this machine;
`--help` lists the rest. Once a single agent remains, lift the order so its commands use every core.
A repository that ships its own runner for heavy commands uses that instead.

## Light change

A **light change** carries out a small ruling or a bug found along the way: one implementer on a
`light/<slug>` branch, merged by you, with no task. Work that needs several tickets or raises a
design question of its own goes to the designer as a task to open. Read
[light-change.md](light-change.md) before writing its brief. A light change that carries out a
decision writes that decision's promotion text in the same branch; tell the designer once it is
merged, so the decision moves to `retired/`.

## Blind evaluation

In an evaluation whose answers are known (a simulation's truth, held-out labels), the executor
works **blind**: its briefs, steers, and readable files carry no truth and nothing derived from it.
Only you compare results with the truth. When a run must be free of earlier leaks, start a fresh
agent for it.

## Hand off and close

An effort that has outgrown its map ends early: when the user says so, or when `check.py` suggests a
hand-off and the user agrees. The designer writes the continuing work as a minimal description: the
Destination, the Staircase steps not yet accepted, and the archived map's path. Its default place is
inside the archived map; the user may name another.

To close, after the last Staircase step is accepted or after a hand-off: confirm with the designer
that the decisions still in the map are promoted, clear `scratch/` as task-flow's Close step 2 does,
and move the map to `.agent_state/archives/maps/<effort-id>/`.

Before telling a task to close, check whether another running task's spec or ticket names a path in
that task's `scratch/`; name those paths in the close message so the task keeps them.
