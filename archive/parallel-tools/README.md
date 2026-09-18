# Archived: parallel-tools extension

Retired 2026-09-18. It registered a `parallel` tool that batched sub-calls to seven
built-ins (`read`, `grep`, `find`, `ls`, `bash`, `edit`, `write`).

## Why

Pi dispatches the tool calls of one assistant message concurrently, which the
provider's own multi-tool-call already expresses. Measured on
`openai-codex/gpt-5.6-terra:medium`, two `sleep 4` bash calls in one response:

```text
native multi-call   both start together, span 4.01s   -> concurrent
parallel tool       8s                                -> sequential
```

`parallel` deliberately sequences any batch containing `bash`, `edit` or `write`,
so for mutating batches it was slower than doing nothing.

Three further problems, all observed rather than theorised:

- **Shared inline budget truncated a result, and absorb then made the truncated
  version permanent.** One run read two ~11K-token files in one `parallel` call;
  the second was capped by `inlineBudget`, and the absorb summary recorded
  "The output for beta.md was capped before its requested entries". Native
  multi-call gives each tool its own budget, so there is no cross-truncation.
- **Two tools were named `parallel`**: this one and the provider's own
  `multi_tool_use.parallel`. An agent asked about workflow friction named this
  first and said it had to infer which one was authorised.
- **Its prompt guideline ("Route every batch through parallel rather than
  emitting the same calls separately in one response") overrode direct user
  instructions.** A session told explicitly not to use the tool used it anyway,
  twice.

The one real loss: `parallel` merged N sub-results into one tool result, so a
batch of reads produced one `[ACP absorb]` marker instead of N. Absorb's `batch`
parameter covers that case in one call.

## What moved with it

Its two test modules and their harnesses, so the live suite stays green.

## Note for a future restore

This copy still reads `globalThis.__piBridgedTools`, the registry that let it
dispatch tools other extensions own (absorb, the subagent tools, the collab
tools). Every publisher was removed after this was archived, so on restore that
path finds an empty registry and only the seven built-ins are dispatchable.
Restoring the bridge means restoring the publishers too.

## Restoring

Move `parallel-tools.ts` back to `home/.pi/agent/extensions/`, move the four test
files back to `tests/`, re-run `setup_scripts/setup_config.sh` to recreate the
symlink, and add `extensions/parallel-tools.ts` back to
`herdrSubagents.allowExtensions` in `home/.pi/settings.json`.
