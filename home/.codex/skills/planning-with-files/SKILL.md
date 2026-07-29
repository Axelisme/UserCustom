---
name: planning-with-files
description: Retired one-release capsule for direct diagnosis of legacy planning records.
user-invocable: false
skill_version: 15
---

# Retired transition capsule

This skill is no longer an active lifecycle authority and must not create or manage new tasks.
Use `dev-flow` and its task-record `scripts/plan.py` for all new durable work.

The preserved `scripts/plan.py` and templates are available for **direct legacy diagnostics only**
during the v136 transition. Invoke the script by its explicit source path when old record bytes
must be inspected. It does not authorize migration, conversion, reinstall, restore, relinking or
new use of the retired schema. Normal setup removes only managed installed planning destinations;
the source capsule remains byte-preserved for this release.
