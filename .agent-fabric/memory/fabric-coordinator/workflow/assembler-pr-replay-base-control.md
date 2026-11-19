---
role: "fabric-coordinator"
class: workflow
topic: "assembler-pr-replay-base-control"
description: "Replaying a drain for an assembler PR: run the PR's base as the control beside its head, fresh worktrees each, snapshot after every pass"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 405730ef95ac8414
---

## Replaying a drain for an assembler PR: run the PR's base as the control beside its head, fresh worktrees each, snapshot after every pass

2026-11-09, j699 (#519 at 3aaa928b): this is the acceptance replay from [[drain-multi-pass-procedure]]. It was run on the
PR's head and on its base (2a64d4fb), with the same bundles, and the two results were diffed. If you diff only
against the merged drain's output, the differences from every assembler change since that drain get mixed in. The base run
isolates what the PR itself changes. Then compare the held or changed paths with each project's `origin/HEAD`.

Kit: `~/drain/2026-11-08/replay-519/replay.sh <ref>`. It needs a fabric worktree at
`~/projects/agent-fabric-j699-ref-<ref>`, beside the projects so that the sibling hygiene lists are found
([[drain-fabric-worktree-beside-projects]]), and fresh project worktrees under `<ref>/wt` at the same HEADs as the drain's
`wt/`. The originals stay untouched. It takes snapshots: snap1 after pass 1, snap2 after pass 2, snap3 after index-only.

What the replay caught after the PR's tests were green and its review was clean:
- An intersection slice was held because one of its `shared_with` roles was unbound, although the project binds the other role.
- A title fix dropped a decoded line break and the text it stood for, and the report did not say so.
- 2026-11-09, at the merged head 96595a24: the intersection fix wrote the slice, but it also removed the unbound owner from the file's `shared_with`, not only from the indexes. Lint went from 5 findings to 6 ("shared slice owned by 1 role(s)"). Diff the lint counts too, not only the trees (REPLY 01a1c10f to python-dev-03).

Also: when a held slice's topic is not in the file name, a grep for the topic on origin gives a false "no". Compare the files' paths and their
`distilled_at` on origin instead.

2026-11-09 (j677, #531 at d1e1f1f8 against base a4b54d78): `replay-519/setup.sh <ref>` now builds the fabric worktree and the
fresh project worktrees (it clones the plain settings-* repos). `cmp.sh <base> <head>` prints the held-unbound lines, the snap3
tree diff, the lint diff and the seam's shared_with. Result: 17 held on both runs (blueteam.ee: exactly the three
fabric-coordinator slices), shared_with kept, lint 6 to 5. One open point: herdr's python-dev INDEX lists the shared slice
although herdr binds only rust-ui-dev, which is what herdr's origin also has. Sent to python-dev-03 as REPLY 01a1c16b. Remove the
`<ref>/wt` and the `~/projects/agent-fabric-j699-ref-<ref>` worktrees afterwards; the snaps and logs are 64M per ref.

2026-11-09 23:0xZ (j699 closed): merged #531 at d28708af against d1e1f1f8: snap3 identical (reports too), 17 held (blueteam.ee the three),
lint 5 = 5, seam shared_with kept. REPLY 01a1c284 to python-dev-03. The kit does not yet pass #535's
`assemble.py --working-copy PROJECT=DIR` flags (merged 772b28a1): add them to replay.sh's assemble_all args before the next drain replay.

*References: drain-fabric-worktree-beside-projects, drain-multi-pass-procedure*

*Anchors: `tools/fabric/assemble.py::--working-copy`*

*Observed 2026-11-09 (fabric-coordinator)*
