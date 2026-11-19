---
role: "python-dev"
class: solution
topic: "j223-hygiene-refusal-merged-544"
description: "assemble refuses a registered project with no working copy (#544); scope choices, the review-brief verbatim slip, arming at minimum 1"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 2401e129ef895300
---

## assemble refuses a registered project with no working copy (#544); scope choices, the review-brief verbatim slip, arming at minimum 1

#544 merged (1 work, 1 fix): `open_layout` in tools/fabric/assembler/intake.py exits 1 when a registered project has no `working_copy_for`; `--allow-missing-hygiene` passes and the report carries `assembled_without_hygiene` (in REPORT_LISTS). The fabric's own project is never missing (its working copy is the root, so no filter needed).

- Scope: a working copy without hygiene.json still counts as found (no checkout on this host has one; refusing would block every drain). `--working-copy PROJECT=DIR` is the anchor guard's only; loading its list there broke test_a_checkout_given_by_working_copy_project_dir (anchor judgement changed). Left to the owner.
- Tests registering a project with no checkout (anchor tests) now pass the flag.
- Re-review request: `fabric-review next` needs `card_base` and the round-1 range ending at the full head sha; dispatch the rendered brief verbatim: retyping long diffs truncated one and I had to stop and redo it.
- Arm at minimum 1 worked from my own session once the review was posted.
- test_leak_check went red in the full suite from a cpu-lease wait (load); passes alone.
**Why:** records scope decisions and traps for the next assembler change.
**How to apply:** extend the check here, not in layout.py; paste briefs from a file read, not from memory.

*Observed 2026-11-10 (python-dev)*
