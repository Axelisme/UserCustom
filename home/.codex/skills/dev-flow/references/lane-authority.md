# Record permissions

Use this reference before granting a writer access to the task record. These permissions are separate
from permission to edit or commit the implementation branch.

## Ticket ownership

The Orchestrator owns ticket prose, acceptance checkboxes, dependencies, state, Resolution, and INDEX.
Writers report progress and evidence to the Orchestrator; reviewers read only.
Checkboxes record the Orchestrator's conclusions, supported by the assigned observations.

Writers may use their assigned ticket's `scripts/` subtree for helpers. Other evidence writes require
an exact target and covered claims in the assignment. Each grant is confined to its named operation
and target. The Orchestrator retains contract edits; persistence mutations require user authority.

## A gate you cannot close honestly

Keep each check's required property intact. When satisfying it exceeds the assigned scope or authority,
report the check, obstruction, and decision needed. This applies to both a delegated writer and the
Orchestrator implementing directly.

## Creating an evidence file

The Orchestrator assigns a fresh target beside the ticket; the writer creates it using
[the evidence template](../templates/ticket/evidence.md). Preserve its Subject, Evidence, and Residuals
sections with actual observations. Use a fresh target for each workflow and preserve earlier evidence.
Updating an existing target requires the assignment to identify it as this workflow's evidence.
Corrections update that assigned file sequentially for the new candidate.

Bind observations to the exact candidate, covered claims, method, results, and limitations. If a
required observation or evidence file remains incomplete, report `BLOCKED`. Evidence creation requires
an assigned path. Routine check output remains with its run.
