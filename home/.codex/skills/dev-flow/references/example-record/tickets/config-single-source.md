# config-single-source — Converge configuration loading onto one source

| Ticket field | Value |
|---|---|
| id | config-single-source |
| status | open |
| depends_on | none |

<!-- status is exactly open | active | closed. When status becomes closed, add a `disposition` row
     directly below it — resolved | superseded | out-of-scope | hard-stop; omit the row while status
     is open or active. -->

**Resolve by:** Implement the admitted Contract-first slice and return one clean exact SHA; user
presence is not required unless a product decision is reached.

## Outcome
Not finished.

## Current

- Observable: the user runs the application at `config load` and sees one merged configuration
  value, sourced from a single owner, instead of the second loader's value silently winning ties.
- Base: `a1b2c3d4e5f60718293a4b5c6d7e8f9012345678` / tree
  `f0e1d2c3b4a5968778695a4b3c2d1e0f9a8b7c6d`.
- Rejected predecessor: an earlier attempt kept both loaders and merged their output at read time;
  rejected because the merge order itself became a second source of truth. Do not patch or collect
  it.
- Contract Red must cover single-owner precedence, missing-file fallback, malformed-file refusal,
  and the prior two-loader regression paths.
- Production direction: one `ConfigLoader` owns the read path; call sites stop importing the legacy
  loader directly.
- Named deletion: `config/legacy_loader.py:LegacyConfigLoader.load`.
- Stop at 300 production lines or return to Root for recut. No second config store, environment
  override layer, or hot-reload mechanism.
- Evidence: `artifacts/config-single-source-source-map.md`.

Machine rework: 0/2.
