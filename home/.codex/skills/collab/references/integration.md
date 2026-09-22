# Integration operations

## Integrate

Inputs are a clean delivery candidate, current integration, candidate-bound observations, and the
owning ticket and review-batch pointers. The Orchestrator checks that the writer stopped, required
ticket gates passed, evidence is complete, and the change stays within authorized scope. Collect ready
branches one at a time while independent tickets continue. Collection assembles work for review; it
does not accept it. Tickets remain pending until their criteria receive batch acceptance.

Use the selected runtime's collection operation. Before it retires a lane, preserve the commit identity
and required evidence with their durable owners. Keep resources needed for unfinished correction or
handoff, or establish their replacement checkout and environment before resuming work.

Reconcile a stale lane with current integration before collection. Resolve conflicts under one writer,
run affected checks, and inspect the new clean delivery candidate. Record introduced interactions for
the owning batch review. Existing review conclusions apply only where their subject and claims remain
applicable; newly affected claims need review on the assembled candidate.

Same-batch dependencies may consume collected pending work under dev-flow's dependency rules. Keep
its unconfirmed obligations explicit. When the batch is ready, run assigned integration gates and
freeze the complete candidate for [Review](review.md#review). If persistence moved, reconcile it into
integration through the runtime route, rerun affected checks, and review imported interactions and
affected task criteria before landing.

Stop collection on conflicts, tracked dirt, candidate mismatch, stale required observations, or missing
ticket gates. Collection is complete when the delivery candidate is included and the ticket names the
assembled candidate, batch owner, observations, and pending obligations. Update INDEX's routing fields
only when integration creates a routing edge.

## Land and clean up

Landing needs a current user message or in-force task grant naming persistence mutation and conditions.
Read dev-flow custody before applying a durable grant. Push needs separate authority. Without landing
authority, stop at reviewed integration.

Before landing, confirm all task changes in the landing candidate have applicable batch acceptance and
required gate observations. An accepted earlier snapshot does not approve subsequently collected work.
Confirm persistence has no staged changes, tracked unstaged changes, or ordinary untracked files.
Reconcile persistence drift into integration and regain applicable judgement before landing. Managed
landing creates a two-parent merge with the previous persistence head first and the judged integration
head second; its tree must equal the judged integration tree.

Inventory owned resources before destructive retirement. Move required evidence to its durable owner,
then remove task-owned temporary files, processes, worktrees, and branches whose purpose is complete.
Managed retirement may delete untracked and ignored lane files. Preserve user state and record every
retained resource's owner and cleanup condition in its ticket or review record. Update INDEX's routing
fields only when landing or retirement creates a routing edge.

Stop on missing authority, persistence dirt, live consumer handoff risk, candidate drift, hook failure,
unaccepted changes, or uncertain custody. Completion requires confirmed integration or landing and
retirement or explicit retention of every execution resource.
