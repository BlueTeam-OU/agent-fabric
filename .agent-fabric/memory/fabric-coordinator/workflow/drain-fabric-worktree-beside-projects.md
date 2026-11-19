---
role: "fabric-coordinator"
class: workflow
topic: "drain-fabric-worktree-beside-projects"
description: "Assembling a drain half against a fabric worktree outside projects/ silently skips every other project's hygiene list"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - acb2d01cbd45ced0
---

## Assembling a drain half against a fabric worktree outside projects/ silently skips every other project's hygiene list

`assemble.py` screens a bundle against every project's hygiene list, and it finds those lists
through the working copies next to the fabric root (`workingcopy.sibling_working_copies`). If
the fabric worktree sits elsewhere, for example in a session scratchpad, it finds no siblings.
The run still exits 0 and reports no redaction, and `lint.py --no-siblings` reports clean as well.
Found 2026-11-05 on gzapp.decks' half of the 2026-10-31 drain (j502, PR #29): gzapp's
`.agent-fabric/hygiene.json` bans the city name. A brand-comms thread kept it because the fabric
worktree was in the scratchpad. The diff against `~/drain/2026-10-31/fixed/wt/gzapp.decks` was the
only thing that showed it. Re-run with the worktree at
`~/projects/agent-fabric-<job>-ref-<sha>`: one redaction, and identical to the control.

**Why:** with no siblings the screen gets weaker, and nothing in the output says so.
**How to apply:** put the fabric-ref worktree beside the projects (`git worktree add --detach
~/projects/agent-fabric-<job>-ref-<sha> <sha>`). Always diff the result against the drain's own
`fixed/wt/<project>` run. Read `redactions` in `last-drain-report.json`, not only the exit code.
A third time on 2026-11-09 (j661, the 2026-11-08 drain onto <city>-shop-transit #5). There the
missing list did more than skip a redaction. The un-redacted topic is a new topic, so the old
`[redacted]` slice stayed as a twin, and the flat `solution.md` was migrated into `solution/`.
A lighter fix also works: export `AGENT_FABRIC_WORKING_COPY=<a gzapp checkout>` for the run.
`layout.working_copy_for` resolves gzapp through it, while the target comes from `--working-copy`.
The result was identical to `~/drain/2026-11-08/wt/<city>-shop-transit`.
See [[drain-project-half-after-fabric-half]] and [[scratch-fabric-worktree-misses-sibling-hygiene]].

2026-11-09 (j588): the same trap catches a corpus-lint control. A
`git worktree add` of origin/main in the scratchpad lints clean (exit 0),
because it never reaches the sibling projects, while the branch worktree
beside them lints red. The valid control is the main checkout
~/projects/agent-fabric at origin/main: it gave the same 114 findings and
exit 1, so the red was already there before the branch.

2026-11-10 (j679): closed in the tool by BlueTeam-OU/agent-fabric#544 (python-dev-01, j223).
A registered project with no known working copy now stops `assemble.py` with exit 1 before it
writes anything, and the message names each project and where it looked. `--allow-missing-hygiene`
lets the run through and lists each one under `assembled_without_hygiene` in the report and on
stderr. Still open: a working copy present without a hygiene.json counts as no list, and
`--working-copy PROJECT=DIR` serves only the anchor guard, so it does not count as found. Both
are left for a later decision. The worktree-beside-projects rule above still applies.

*References: drain-project-half-after-fabric-half, scratch-fabric-worktree-misses-sibling-hygiene*

*Anchors: `tools/fabric/assembler/intake.py::sibling_working_copies`*

*Observed 2026-11-10 (fabric-coordinator)*
