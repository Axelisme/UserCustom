# Herdr first-prompt workaround

Temporary repair for the empty first system prompt observed with Pi 0.87.0 when
pi-herdr-subagents starts a child through `sendMessage({ ... }, { triggerTurn: true })`.
It does not resend a request or execute tools. It uses `context_with_system` to copy
`ctx.getSystemPrompt()` into an otherwise empty request prompt, before provider delivery.

The plugin activates only when both managed-child environment IDs are present and
the configured prompt contains nonempty `subagent_role_guidance` and
`subagent_dispatch` blocks. Existing nonempty prompts, including restored system
patches, remain untouched. Partial or conflicting nonempty prompts are deliberately
not repaired. Tool declarations remain intact; the repair writes no session entries,
files, settings, or runtime state. It can repair another empty request after resume;
it is not limited to a process's first request.

## Enable

The repository's `home/.pi/agent/settings.json` has one entry at the end of
`herdrSubagents.allowExtensions`:

```text
/home/axel/UserCustom/home/.pi/agent/workarounds/herdr-first-prompt/index.ts
```

This explicit path loads the plugin last among the currently allowlisted extensions.
No global extension symlink or package installation is needed. If this repository
moves, update the path. Herdr reloads its allowlist on each fresh child launch and
replacement resume. Already-running children retain their loaded extensions.

## Disable or remove

1. Remove only the path above from `herdrSubagents.allowExtensions` in
   `~/.pi/agent/settings.json`, which currently links to this repository's settings.
2. Future child launches and replacement resumes no longer load the workaround.
   Already-running children keep it until they exit; restarting only the parent does
   not replace a surviving child.
3. Optionally delete this entire `herdr-first-prompt/` directory and
   `tests/herdr_prompt_workaround.test.mjs`. Remove the allowlist entry **before**
   deleting the plugin, otherwise Herdr rejects launches with a missing extension.

There are no other registrations or stored state to clean up. An upstream repair that
supplies a nonempty prompt makes this plugin a no-op; remove it once that behavior is
verified on the installed Pi version. It does not inspect or pin the version number.

## Verification

From the repository root:

```sh
PI_OFFLINE=1 node --test tests/herdr_prompt_workaround.test.mjs
```

The test uses the installed Pi SDK and a local faux provider. It does not start a Pi
subprocess, contact remote models, or modify user sessions. Set `PI_TEST_PACKAGE_ENTRY`
to another installation's `dist/index.js` if needed. The disabled case records upstream
behavior but does not require the bug to remain present after a Pi upgrade.

The repair runs at Pi's full-context hook, not on serialized provider payloads. An
extension loaded later can still rewrite the request. No live Herdr/remote-provider
end-to-end verification is claimed by these tests.
