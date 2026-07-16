---
orchestrate_compat: 66
---

# Immutable dispatch packets

Use a packet when an inline frozen contract would obscure the immediate action, especially
for a hard-critical slice or exact-SHA review. This is prompt indirection, not a new control
plane: the direct collaboration message grants authority and names the packet; file existence
does not authorize execution.

## Boundary

Packets are immutable, content-addressed task artifacts under:

```text
.agent_state/orchestrate/<task-id>/packets/<SHA-256>.md
```

Root publishes a packet and sends the assigned identity its absolute path, SHA-256, role,
explicit authority, and immediate stop condition. The consumer verifies the hash and basis
before acting. A stale, malformed, unreferenced, or hash-mismatched packet is inert.

Packets carry frozen input only. They never carry milestones, findings, current phase,
completion, collection authority, or landing state. Root may replace a contract only by
publishing new content and directly authorizing its new hash; published content is not edited.

## Format

The strict envelope is deliberately small:

```text
---
dispatch_packet_version: 1
packet_id: critical-slice-a
role: planner|writer|reviewer
basis_sha: <exact commit SHA>
hard_critical_axes: none|hardware|persistence|security|atomic-cutover[, ...]
---
```

The Markdown body contains these headings, each with concise task-specific content or
`none`:

- `## Authority` — what the role may write/decide and what remains root/user-owned.
- `## Acceptance` — externally observable completion conditions and commands.
- `## Non-goals` — explicit exclusions that prevent scope growth.
- `## Exact literals` — schema names, status codes, protocol values, or `none`.
- `## Oracles` — independent expected values and dangerous failure probes.
- `## Review policy` — hard axes, named risks, cadence/waiting, or `none`.
- `## Stop conditions` — when to report instead of improvising.

For a security hard-critical packet, `Oracles` should state the adversary capability and
containment level: public API, serialization, or in-process reachability. Name whether private
attributes, closures, bound owners, and nested object graphs are inside the oracle. This is a
conditional threat-model lens, not a universal checklist for unrelated work.

## Adapter and lifecycle

```text
orchestrate packet publish --root <repo> --task-id <task> --input <packet.md>
orchestrate packet inspect --root <repo> --task-id <task> --sha256 <hash>
```

`publish` validates the envelope, required headings, exact basis commit, UTF-8, Git ignore,
and release compatibility before an atomic content-addressed write. Republishing identical
content is idempotent. `inspect` is read-only and verifies filename/content identity; neither
command infers readiness, dispatch, or authority.

The packet may be removed after every referenced role has reached a terminal milestone and
root no longer needs it for recovery. Cleanup is ordinary task-artifact maintenance, never a
workflow transition. A cross-session handoff records the path/hash pointer in current state;
the next root revalidates before redispatch.
