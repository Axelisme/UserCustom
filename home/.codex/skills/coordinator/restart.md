# Planned restart

Reached from the coordinator's [Resume](SKILL.md#resume) when the user announces a machine restart
with a time.

## Before

1. Send every running task a `steer` naming the restart time and task-flow's planned-restart clause
   ([Mapped tasks](../task-flow/SKILL.md#mapped-tasks)); give a checkpoint deadline two minutes
   before the restart. Tell each designer to file its open topic and reply `restart-ready`.
2. Write `scratch/coordinator-resume/restart-<date>/RESUME.md`:
   - the herdr name, pane, and agent kind of every live agent;
   - for each task, its state and the checkpoint path it reports;
   - what waits on the user;
   - the rules that stay in force (grants, protected files, memory limits).
3. Add each `blocked(<task>): checkpoint <path>` to `RESUME.md` as it arrives. Timestamps come from
   `date`.

## After

1. Read `RESUME.md`, then run [Resume](SKILL.md#resume): names, patrol schedule, Follow-ups.
2. Send each task and designer one `steer` to continue from its checkpoint. A run the restart
   interrupted is not evidence and uses up no retry or once-only grant; only exclusive work and work
   past the grant needs a new grant.
