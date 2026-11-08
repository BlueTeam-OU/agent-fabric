---
role: "python-dev"
class: solution
topic: "replay-key-compare-claim-body-as-written-link-pointing"
description: "assembler replay drop (j82): a recorded replaced_key is over the text as written; a run that points [[links]] rewrites every claim body, so compare the body as written too"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: "python-dev-04"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 20a3aac63ab4a356
---

## assembler replay drop (j82): a recorded replaced_key is over the text as written; a run that points [[links]] rewrites every claim body, so compare the body as written too

j82 / PR 445 (2026-11-01). `drop_replayed` drops a claim whose (heading, section_key) an earlier correction replaced. Three traps that only the real drain showed:

- **Old reports hold only `applied_corrections`** (slice, `replaced`, `replaced_key`), no `replaced_sections`: read both, the home of a legacy entry from the slice path (`_in_home`).
- **Link pointing changes the claim's key.** `targets.point` rewrites `[[memory]]` in every claim body of a run when that memory was merged into another slice; the recorded key was taken over the text before. The claim now keeps `_body_as_written` and the drop compares both keys. A test that records the correction in a run *before* the linked memory is merged reproduces it (herdr's second pass, REPLACED SECTION STANDS); built in the other order it passes without the fix.
- **A stderr note beats a guess.** When the drop did not fire I added `reharvested_replaced` (claim key and replaced keys on stderr and in the report) and asked the requester to replay once: the line decided the cause in one round.

**Why:** two replays of the real bundles each needed a different fix than the synthetic tests suggested. **How to apply:** for a convergence bug, build the fixture in the same run order as the real drain and add a diagnostic note before theorising; a key computed over a text is only as stable as every rewrite of that text between runs.

Also: `fabric-review next` on a later round needs `card_base` in the request and `range` = last base..last reviewed head (full shas); a 60 KB brief can go to the reviewer as a file path plus the dispatch header.

*References: memory*

*Anchors: `tools/fabric/assembler/shapes.py::drop_replayed`, `tools/fabric/assembler/targets.py::resolve_targets`*

*Observed 2026-11-01 (python-dev)*
