# Make Grove available

Setup may mutate the user's global installation or shared grammar cache. Inspect
first; perform those mutations only with current user authority.

1. Run `command -v grove` and `grove --version`.
   - If the binary is missing, report the blocker and offer the official
     installer or `npm i -g @entelligentsia/grove`; let the user choose the
     installation method.
2. Run `grove languages` and confirm that the target extension is claimed.
   - If a catalog grammar has not been downloaded and cache/network mutation is
     authorized, run `grove fetch <lang>`.
   - If no catalog grammar covers the language, use text tools.
3. Retry the narrow navigation command that triggered setup.

Setup is complete when `grove --version` succeeds and the target command can
load its grammar, or when the exact missing capability and the command the user
would need to authorize are reported.

`grove init` configures project integration; CLI navigation does not require it.
`grove doctor` audits that integration, so integration warnings do not by
themselves show that the CLI is unusable.
