# Orchestrate — Codex runtime binding

Codex uses the native tools exposed by the current session. This document maps the v119
roles without emulating runtime state.

## Dual-role native agents and terminal handoff

Run two persistent native role agents per Wave: `wave-oracle` authors the public Interface,
contract tests, fixtures, and intended red Contract; `wave-implementer` fills shared
production paths after Root merges the exact Contract SHA. Native messaging, follow-up, and
continuation are used when available in v1 and v2. A terminal `slice-ready` message carries
Slice and exact 40-character SHA and immediately end the role's turn. In degraded v1,
commit trailers (`Slice`, `SHA`, `Seam-Ready`) are the handoff.

Codex has no simulated queue. Root owns dependency depth and placement. After restart or
compaction, recover pending position from the task plan and Git refs/history.

## Native generations

In v1, `spawn_agent` loads the named profile and `send_input` is notification; use
`resume_agent` for same-identity continuation. In v2, `spawn_agent` is generic and native
`send_message`/`followup_task` provide messaging and continuation. `wait_agent` is the event
wait in either generation. Identify the observed tool generation at session start and do not
invent a missing capability.

## Profile bootstrap and safety

At first use, verify the role profile instructions are active. Every dispatch names exact
cwd, frozen base or subject SHA, write scope, pre-existing dirt, required evidence, and stop
conditions. Workers do not create child workers or claim repository authority. Root proves
clean Git state before consuming a handoff.

## Acceptance

Dev-flow runs simplify, canonical tests, and one clean-detached exact-SHA code-review. A
behavior correction returns to Oracle then Implementation in the same Wave; a quality
correction returns to Implementation. Repository integration requires current user authority
and is outside the workflow CLI.
