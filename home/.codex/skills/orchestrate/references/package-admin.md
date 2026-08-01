# Orchestrate — Package administration

`doctor` verifies the executing package's current manifest, documents, profile identity/prompt
projections. v137+ profile entries contain only `agent_name` and
`prompt_sha256`; runtime, model, and configuration metadata are excluded. `doctor --path <repo>`
adds the cwd-derived repository pin projection.
`doctor diff <old> <new>` compares only bundled immutable manifests; `--runtime codex|claude|pi`
filters runtime-specific documents, profiles, and assets. `pin status` and the atomic idempotent
`pin set` derive the repository from cwd. A pin records the last manually adopted release; it never
selects the executable or blocks task work merely because it is absent or different.

`release --version <exact-next>` is the sole package publication command. It requires an intact
current package — its manifest loads and lists no missing document — and an exact-next migration
guide. It does not require the current package to still match its own hashes, because publication
edits exactly those documents. It updates the source identity, writes the target manifest, verifies
the published result against it, and restores prior bytes on failure. Apply manifest-hashed
migration guides in order before a separately authorized setup or pin change.
