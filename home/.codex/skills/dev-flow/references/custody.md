# Dev-flow — custody

The record holds the user's authority in **custody**; it creates none.

**Surface new grants.** List new standing-order entries in the same reply so the user can disown
them immediately.

**Admit durable grants.** An order is authority that still binds after the requested act completes.
Test it with: *doing this, does the sentence go away?* The work itself records one-off instructions.
When one sentence combines an act and a durable grant, admit it for the grant and quote the whole
sentence.

**Resolve ratification by address.** Before asking for assent, persist the proposal; then store the
user's quote and a pointer to that frozen text. Amendments require new ratification rather than
editing the assented text. If no antecedent was recorded, preserve it under an explicit
`reconstructed` label.

**Keep verbatim quotes on one line.** A verbatim `「...」` quote must open and close on one physical line because line wrapping makes exact custody ambiguous.

**Retire by user authority.** An order lapses only when its stated condition fires, a later user
message revokes or replaces it, or the task is archived. Move it intact to the retired record with
date and reason. Keep overlapping orders separate: the newest governs addressed points and all
other in-force clauses remain. Ask whether an ambiguous new order narrows or replaces an old one.

**Apply the Envelope.** Out-of-envelope decisions follow the task record's `Envelope` pointer to its
frozen artifact and cite that artifact, not the pointer slot itself.

**Mutate from user authority.** A custody change requires either a current user message or an
in-force task-scoped user grant that names that mutation and whose conditions hold. The record
preserves a prior grant without extending it. When a grant activates another skill, point to that
skill's contract for its grants and exclusions.
