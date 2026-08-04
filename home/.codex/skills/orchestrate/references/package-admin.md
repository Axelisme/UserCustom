# Orchestrate — Package administration

`doctor` verifies the executing package's current manifest, its documents, and its profile
identity and prompt projections. A profile entry carries only `agent_name` and `prompt_sha256`;
runtime, model, and configuration metadata are excluded, so changing a profile's model is not a
package change. `doctor --path <repo>` adds the cwd-derived repository pin projection.
`doctor diff <old> <new>` compares only bundled immutable manifests; `--runtime codex|claude|pi`
filters runtime-specific documents, profiles, and assets. `pin status` and the atomic idempotent
`pin set` derive the repository from cwd. A pin records the last manually adopted release; it never
selects the executable or blocks task work merely because it is absent or different.

`release --version <exact-next>` is the sole package publication command. It requires an intact
current package — its manifest loads and every document it lists is present — and an exact-next
migration guide. Removing a document requires naming it with a repeatable `--drop <path>`: an
absent file is the only evidence either way, so a deliberate deletion and a lost file look
identical and the intent is declared rather than inferred. A `--drop` that names something outside
the current manifest, or something still on disk, fails the preflight. It does not require the current package to still match its own hashes, because publication
edits exactly those documents. It updates the source identity, writes the target manifest, verifies
the published result against it, and restores prior bytes on failure. Apply manifest-hashed
migration guides in order before a separately authorized setup or pin change.
