---
role: "python-dev"
class: workflow
topic: "assembler-two-runs-one-out-supersede-and-sibling-fixture"
description: assembler test with a control run then a flag run in one out dir stops on SUPERSEDING; sibling fixture = git init + marker file beside out
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 790dc027712c1d06
---

## assembler test with a control run then a flag run in one out dir stops on SUPERSEDING; sibling fixture = git init + marker file beside out

j129 (#622, merged 2026-11-15): a test that runs assemble twice on the same `out` with the same claim writes nothing the second time and exits 1 ("SUPERSEDING?"), because the first run's slice differs from what the second would write. Remove `dom(out, role)` between runs.

A registered project "found beside the tree" in a test needs a directory beside `out` (so under `tmp`), `git init`, `.agent-fabric/memory/`, and an `.agent-fabric-project` file naming the id (`workingcopy.MARKER`); `sibling_working_copies` resolves by marker or remote.

`fabric-review next` on a first request written `range: origin/main..HEAD` refuses ("head 'HEAD' is not a commit id"): pin the request's range to the two shas before deriving the re-review brief.

**Why:** each cost a failed run or a refused render.
**How to apply:** pin shas in the review request after round 1; clean the slice dir between runs of one fixture.

*Anchors: `tests/test_assemble.py::test_a_named_checkout_outranks_one_found_beside_the_tree`, `tools/fabric/workingcopy.py::MARKER`*

*Observed 2026-11-15 (python-dev)*
