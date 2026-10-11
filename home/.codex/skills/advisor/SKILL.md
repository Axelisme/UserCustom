---
name: advisor
description: "Advise on an effort larger than one task: hold its map, rule on design with the user, open task-flow tasks, and coordinate them over herdr."
disable-model-invocation: true
---

# Advisor

An **effort** is work too large for one task. You are its **advisor**: you discuss design with the
user, record rulings, open [task-flow](../task-flow/SKILL.md) tasks for the parts whose design is
clear, and coordinate those tasks while they run. Task Orchestrators implement; you never write
code or task records after hand-off.

## The map directory

An effort lives at `.agent_state/maps/<effort-id>/` in the main checkout. You are its only writer.

| Path | Holds |
|---|---|
| `MAP.md` | `## Destination`, `## Staircase`, `## Tasks`, `## Not yet specified`, `## Out of scope`, `## Standing orders` |
| `design.md` | The effort's current design, as a to-spec entry file |
| `design/<topic>.md` | Design detail behind a conditional pointer in `design.md` |
| `decisions/NNNN-<slug>.md` | One ruling: the reason behind design text |
| `retired/`, `scratch/` | As in task-flow |

`python3 <skill-dir>/scripts/check.py <map-dir>` reports structure violations and lists the
decisions awaiting the user's review.

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
2. Run `herdr agent list` and match every `running` Tasks line to a live agent name. For a lost
   name, ask the user which pane runs the task, then `herdr agent rename <pane> <name>`; restore your
   own name the same way.
3. List each running task's `scratch/questions/`; every file there is a question awaiting a ruling.

## Chart the effort

1. Settle the Destination with grilling and domain-modeling.
2. Write the Staircase with the user.
3. Write `design.md` from the discussion; sketch the rest into Not yet specified.
4. [Suggest grants](#suggest-grants) for how this effort runs.

Charting is done when the user has accepted the Destination and Staircase, and the first step's
design is clear enough to slice.

## Open a task

1. Choose a Staircase step whose design is settled. When it needs code from an unlanded task, that
   task is its Base (task-flow [stacked tasks](../task-flow/SKILL.md#stacked-tasks)).
2. Create the task directory per task-flow. INDEX Goal holds the step's sentence,
   `Map: <map-dir>`, and `Base:` when stacked. The task has no `decisions/`; the map holds them.
3. Write the task's `spec.md` with to-spec, covering only this task's slice and pointing to map
   design by condition instead of copying it. Slice it with to-tickets. The user confirms both.
4. Add the Tasks line as `planned` and ask the user to start an agent for it. Once it runs, name it
   with `herdr agent rename <pane> <name>`, mark the line `running`, and send it
   `start(<task-id>): <task-dir>`.

The task's Orchestrator owns its spec and tickets from then on.

## Messages

Messages go through `herdr agent prompt <name> "<message>"` and carry pointers, never content.

| Direction | Message | Meaning |
|---|---|---|
| task → advisor | `question(<task>): <one line>; <scratch path>` | A design question; scenario and options in the file |
| advisor → task | `ruling(<task>): decisions/NNNN` | Answered; the task updates its spec to match |
| advisor → task | `design-change(<task>): decisions/NNNN` | A ruling elsewhere changes this task's design |
| advisor → task | `base-landed(<task>)` | Retarget and pull |
| task → advisor | `review-done(<task>): <report path>` | Land review finished; landing waits on you |
| advisor → task | `land(<task>): 「<user's words>」` or `land(<task>): STDO <date>` | Land, on the quoted instruction or the named grant |
| task → advisor | `landed(<task>)` or `blocked(<task>): <one line>` | Status |

## Answer a question

1. Read the question file, the design it touches, and the decisions governing that design.
2. With the user present, ask in the reply with scenario, options, and a recommendation; record the
   answer as a decision. With the user away, rule by proxy if a standing order covers the question;
   otherwise tell the task it waits on the user and hold the question for their return.
3. In the same write, update the design and retire superseded decisions. Send `ruling` to the asking
   task and `design-change` to every other running task whose spec points into the design text that
   moved.

A **proxy ruling** is a decision whose header reads `Ruled-by: advisor (STDO <date>)` and
`Review: pending`, followed by the reasoning, an example, and the cost of the adopted option in
place of the user's answer. It binds tasks like any decision.

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
- A **patrol**, when a standing order or the user asks for one, checks each running task: its herdr
  state (`herdr agent get`), `check.py` on its task directory for frontier and `doing` tickets, and
  its `scratch/questions/` for questions you have not answered. Report idle or blocked tasks to the
  user; prompt an idle task with its frontier ticket numbers.

## Suggest grants

The user grants authority; you suggest what to grant. Suggest when charting, when the user says
they are leaving, and when the same kind of question reaches the user a second time. Each suggestion
names the scope, the conditions, what stays with the user, and when it lapses, worded so the user
can send it back with `STDO:`. Common grants:

- **Proxy rulings** on task design questions while the user is away. Keeps with the user: Staircase
  acceptance, push, hardware, real data, skills. Lapses when the user returns.
- **Landing** a task's integration when land review findings are resolved, gates are green, and the
  target merges cleanly; report afterwards. Push stays with the user.
- **Task spec changes without a ruling** for gaps that contradict no decision; the task notifies the
  advisor and continues.
- **Patrol** at a stated interval.
- **Time budget** per task as a planning signal: on expiry the task notifies the advisor and
  continues; the advisor may extend.

## Close the effort

When the last Staircase step is accepted: promote the map's decisions and `design.md` as task-flow's
Close step 1 does, delete `scratch/`, and move the map to
`.agent_state/archives/maps/<effort-id>/`.
