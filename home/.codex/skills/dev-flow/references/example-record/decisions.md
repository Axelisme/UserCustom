# Current decisions

## Authority and scope

- Configuration reads go through exactly one `ConfigLoader`; no second loader survives.
- Only the current single-source need is in scope; a future remote config service is out of scope.

## Git state

- Work proceeds on a task branch; no ref has been pushed or landed.

## Delivery frontier

- `config-single-source` is the only implementation ticket; nothing is collected yet.

## Current decisions

- The legacy loader's tie-break order is not preserved; the new owner's precedence is documented in
  the ticket, not re-derived here.
