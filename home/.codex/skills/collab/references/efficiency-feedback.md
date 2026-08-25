# Collab efficiency feedback — Pi shared guidance

This reference owns the optional `efficiencyFeedback` content standard for Pi worker (`collab-implementer`) and reviewer (`collab-acceptor`) when a dispatch requests it.

When a dispatch requests native `efficiencyFeedback`:

- Report the single most useful observed and avoidable cost.
- Name its concrete cause.
- Include measured duration or extra search range when available.
- Omit the field when no avoidable cost was observed.
- Exclude ordinary passed-test lists, lane cleanliness, changed-file counts, and review receipts unless they directly demonstrate avoidable work.

When a dispatch does not request `efficiencyFeedback`, omit the field entirely; do not invent receipt-only content.

This reference does not define JSON shape, length limits, routing isolation, storage, verdict, coverage, telemetry, or terminal projection; those remain with `home/.codex/skills/collab/runtime-pi.md` and the runtime schema.
