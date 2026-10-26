---
name: advisor
description: "Advise on an effort larger than one task: hold its map, rule on design with the user, open task-flow tasks, and coordinate them over herdr."
disable-model-invocation: true
---

# Advisor

An **effort** is work too large for one task. You are its **advisor**: you discuss design with the
user, record rulings, open [task-flow](../task-flow/SKILL.md) tasks for the parts whose design is
clear, and coordinate those tasks while they run. Implementers write the code: each task's
Orchestrator and its lanes, and the one implementer of a [light change](#light-change), whose branch
you merge. You write the map; a task's records belong to its Orchestrator from hand-off.

## The map directory

An effort lives at `.agent_state/maps/<effort-id>/` in the main checkout. You are its only writer.

| Path | Holds |
|---|---|
| `MAP.md` | `## Destination`, `## Staircase`, `## Tasks`, `## Not yet specified`, `## Out of scope`, `## Standing orders` |
| `design.md` | The effort's current design, as a to-spec entry file |
| `design/<topic>.md` | Design detail behind a conditional pointer in `design.md` |
| `decisions/NNNN-<slug>.md` | One ruling: the reason behind design text |
| `retired/`, `scratch/` | As in task-flow |

`python3 <skill-dir>/scripts/check.py <map-dir>` reports structure violations, lists the decisions
awaiting the user's review, and prints `hand-off suggested:` once the map outgrows one advisor (see
[Hand off the effort](#hand-off-the-effort)).

- **Destination**: one or two lines naming where the effort ends.
- **Staircase**: the ordered states the user can see and accept on the way, one sentence each in
  the user's terms ("the user does X and sees Y"), five to nine steps.
- **Tasks**: first line `Advisor: <herdr-name>`, then one line per task:
  `- <task-id> — step <n> — Base: <task-id|none> — herdr: <name> — planned|running|landed`.
- **Not yet specified**: in-scope design you cannot yet phrase as a question.
- **Out of scope**: work ruled beyond the Destination, one line each with the reason.
- **Standing orders**: as in task-flow, plus the [grants you suggested](#suggest-grants) once the
  user marks them `STDO:`. They bind every task of the effort. An order whose lapse condition is met
  moves to `retired/` with the date it lapsed.

**Design** is the current state; **decisions** are the reasons. Every ruling updates the design text
it changes in the same write, so a task reads design and never needs a decision. Write decisions as
task-flow does (first line `Supersedes:`, the question as asked, the adopted option in full, the
answer verbatim in 「」, rejected options one line each, superseded files moved to `retired/`).

## Resume

After compaction, a session change, or a herdr restart:

1. Read `MAP.md` whole and run `check.py`.
2. Run `herdr agent list` and match every `running` Tasks line, and every unmerged
   `git branch --list 'light/*'`, to a live agent name. For a lost name, ask the user which pane runs
   the work, then `herdr agent rename <pane> <name>`; restore your own name the same way.
3. List each running task's `scratch/questions/`; every file there is a question awaiting a ruling.
4. Re-create the [patrol](#patrol) schedule when a standing order grants one.

MAP.md lags behind Git. Before you list open work to the user, confirm each item against `git log`
and the files it names, and update MAP.md for items already done.

## Chart the effort

1. Settle the Destination with grilling and domain-modeling.
2. Write the Staircase with the user.
3. Write `design.md` from the discussion; sketch the rest into Not yet specified.
4. [Suggest grants](#suggest-grants) for how this effort runs.

Charting is done when the user has accepted the Destination and Staircase, and the first step's
design is clear enough to slice.

## Open a task

1. Choose every Staircase step whose contract is settled: its design, and its interfaces to the
   steps beside it. They open together. A step stacks on an unlanded task only when it needs that
   task's code (task-flow [stacked tasks](../task-flow/SKILL.md#stacked-tasks)); tasks that touch the
   same files still run in parallel and resolve conflicts at landing.
2. Create the task directory per task-flow. INDEX Goal holds the step's sentence,
   `Map: <map-dir>`, and `Base:` when stacked. The task has no `decisions/`; the map holds them.
3. Write the task's `spec.md` with to-spec, covering only this task's slice and pointing to map
   design by condition instead of copying it. Slice it with to-tickets. The user confirms both.
4. Add the Tasks line as `planned`. Give the task its own workspace
   (`herdr workspace create --cwd <repo> --label <task-id> --no-focus`) and an agent on a clean
   context: start one there with `herdr agent start`, ask the user to start one, or `/new` an idle
   agent after moving its pane in with `herdr pane move`. Name it with
   `herdr agent rename <pane> <name>` once it runs and again after every `/new`, mark the line
   `running`, send `start(<task-id>): <task-dir>`, and confirm the agent turns `working`.

The task's Orchestrator owns its spec and tickets from then on. Run one agent per running task and
per light change in flight.

## Messages

Messages go through `herdr agent prompt <name> "<message>"` and carry pointers, never content.

| Direction | Message | Meaning |
|---|---|---|
| task → advisor | `question(<task>): <one line>; <scratch path>` | A design question; scenario and options in the file |
| advisor → task | `ruling(<task>): decisions/NNNN` | Answered; the task updates its spec to match |
| advisor → task | `design-change(<task>): decisions/NNNN` | A ruling elsewhere changes this task's design |
| advisor → task | `steer(<task>): <provenance>; <process instruction>` | Process guidance within existing scope, acceptance, and grants |
| advisor → task | `base-landed(<task>)` | Retarget and pull |
| task → advisor | `review-done(<task>): <report path>` | Land review finished; landing waits on you |
| advisor → task | `land(<task>): 「<user's words>」` or `land(<task>): STDO <date>` | Land, on the quoted instruction or the named grant |
| task → advisor | `landed(<task>)` or `blocked(<task>): <one line>` | Status |

Before sending `steer`, read the receiving contract in task-flow's
[Mapped tasks](../task-flow/SKILL.md#mapped-tasks) and check the message against its provenance and
authority requirements. Link supporting evidence when needed.

Read what every `herdr agent prompt` returns: `agent_not_found` means the name was lost, so rename
the pane and resend. To the user, call each agent by its herdr name.

## Answer a question

1. Classify the question. Process, coordination, verification method, and bugfix questions are
   yours: rule, and reply `steer(<task>): advisor-observation; answers <question path>: <instruction>`.
   They leave no decision and never reach the user's review. Design questions (behaviour, interface
   meaning, data format, scope) continue below.
2. Read the question file, the design it touches, the decisions governing that design, and the
   repository's ADRs on that area. Where none governs, follow the closest ADR or decision as
   precedent.
3. With the user present, ask in the reply with scenario, options, and a recommendation; give each
   option its implementation cost and the parts that could be cut. Record the answer as a decision.
   With the user away, rule by proxy if a standing order covers the question; otherwise tell the
   task it waits on the user and hold the question for their return.
4. In the same write, update the design and retire superseded decisions. Send `ruling` to the asking
   task and `design-change` to every other running task whose spec points into the design text that
   moved.

When a task's second question about a verification method, threshold, or rigor arrives, ask the user
what the purpose needs ("runs end to end" or "meets a stated precision bar") before ruling another
guard. Record that acceptance level as a decision; later method questions rule against it.

A **proxy ruling** is a design decision whose header reads `Ruled-by: advisor (STDO <date>)`,
`Review: pending`, and `Precedent: <the ADRs and decisions you read>`, followed by the reasoning, an
example, and the cost of the adopted option in place of the user's answer. It binds tasks like any
decision.

## When the user returns

Open with the pending list from `check.py`, one ruling at a time, presented like a question:
scenario, the adopted option, its reasoning, example, and cost. An accepted ruling keeps its
reasoning, gains a body line `Answer: 「<user's words>」`, and its header becomes `Review: accepted`. An overturned one is superseded by a new decision,
which goes out as `design-change` to the affected running tasks. When an affected task has already
landed, the change becomes part of a planned task or opens a new one. After the pending rulings,
bring the questions you held while the user was away.

## Coordinate

- On `review-done(<task>)`: present the report to the user. With the user's instruction, or a
  standing order that grants landing, send `land(<task>)` quoting that authority.
- On `landed(<task>)`: mark the line `landed` and send `base-landed` to every task stacked on it.
- On `blocked`: settle what is yours to rule; bring the rest to the user.

## Patrol

A **patrol** runs when a standing order or the user asks for one. Keep one patrol schedule, hourly
unless the order names an interval. A Claude Code cron lives only in your session and expires after
seven days, so on [resume](#resume) list the existing schedules and create one only when none
remains.

Each pass:

1. Run `python3 <skill-dir>/scripts/patrol.py <map-dir>`. For each running task it prints the herdr
   state, frontier and `doing` tickets, unanswered questions, scratch size, the size of any Python
   harness in scratch, and a tail for idle agents.
2. Report idle or blocked tasks to the user; prompt an idle task with its frontier ticket numbers.
   Restore a missing name as in [Resume](#resume).
3. Spot-check one task per pass, rotating through them: every `done` ticket has its acceptance
   checked or an evidence path; same-kind slices run as one batch; nothing is built beyond its
   ticket; a flagged harness becomes one 100–200 line script that reuses existing tools; a harness
   that broke on its own bug three times is walked by hand once before it is automated again; and
   `git worktree list` holds no worktree for a lane already collected or dropped. Steer what you find.

## Shared machine

While more than one agent runs heavy commands (full test suites, simulations, benchmarks), suggest a
standing order that routes each through
`python3 <skill-dir>/scripts/slot.py <timeout-seconds> -- <command>`. It queues the command for a
CPU slot shared by every worktree of the repository, pins it to that slot's cores, and starts it
once MemAvailable allows. The order names `--slots`, `--cores`, and `--min-ram-gb` for this machine;
`--help` lists the rest. Once a single agent remains, lift the order so its commands use every core.
Loosen limits one task at a time, about ten minutes apart, reading MemAvailable from the
[patrol](#patrol) between steps.

## Suggest grants

The user grants authority; you suggest what to grant. Suggest when charting, when the user says
they are leaving, and when the same kind of question reaches the user a second time. Each suggestion
names the scope, the conditions, what stays with the user, and when it lapses, worded so the user
can send it back with `STDO:`. Common grants:

- **Proxy rulings** on task design questions while the user is away. Keeps with the user: Staircase
  acceptance, push, hardware, real data, skills, and UI acceptance that needs a desktop walkthrough.
  Lapses when the user returns.
- **Landing** a task's integration when land review findings are resolved, gates are green, and the
  target merges cleanly; report afterwards. Push stays with the user.
- **Task spec changes without a ruling** for gaps that contradict no decision; the task notifies the
  advisor and continues.
- **Patrol** at a stated interval.
- **Time budget** per task as a planning signal: on expiry the task notifies the advisor and
  continues; the advisor may extend.

## Light change

A **light change** carries out a small user ruling or a bug found along the way: one implementer on
a `light/<slug>` branch, merged by you, with no task. Work that needs several tickets or raises a
design question of its own opens a task instead. Read [light-change.md](light-change.md) before
writing its brief.

## Blind evaluation

In an evaluation whose answers are known (a simulation's truth, held-out labels), the executor
works **blind**: its briefs, steers, and readable files carry no truth and nothing derived from it.
Only you compare results with the truth. When a run must be free of earlier leaks, start a fresh
agent for it.

## Design research

A design question with several independent angles or options is researched by **fan-out**, and a
feasibility question by a **spike**. Read [research.md](research.md) before dispatching either.

## Hand off the effort

An effort that has outgrown one advisor ends early: when the user says so, or when `check.py`
suggests a hand-off and the user agrees. Write the continuing work as a minimal description where
the user names: the Destination, the Staircase steps not yet accepted, and the archived map's path.
Leave design detail and method to the next advisor and the user. Then close the effort.

## Close the effort

When the last Staircase step is accepted, or after a hand-off: promote the map's decisions and
`design.md` as task-flow's Close step 1 does, clear `scratch/` as task-flow's Close step 2 does, and
move the map to `.agent_state/archives/maps/<effort-id>/`.

Before telling a task to close, check whether another running task's spec or ticket names a path in
that task's `scratch/`; name those paths in the close message so the task keeps them.
