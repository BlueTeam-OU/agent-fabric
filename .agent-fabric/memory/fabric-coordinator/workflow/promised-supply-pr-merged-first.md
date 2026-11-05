---
role: "fabric-coordinator"
class: workflow
topic: "promised-supply-pr-merged-first"
description: "a job says \"commit onto their branch\" but their PR merged first — the commit rides my own open PR and the contributor is told so"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - b12cfa3702b6b92e
---

## a job says "commit onto their branch" but their PR merged first — the commit rides my own open PR and the contributor is told so

j552 (queued 2026-11-01) said to supply ADR-053's rule-2 amendment as a commit onto python-dev-02's #455 branch.
By the time the job started (2026-11-05), #455 had merged (2026-11-02, d56a133c) without it. Check
`gh pr view <n> --json state` before preparing a supply. If it is MERGED, the amendment is a `Kind: work` commit on
my own open PR (here c6b9a464 on #488, see [[next-work-rides-the-open-pr]]). Then send a REPLY to the contributor
saying where it landed: they had told others it would land on their branch.

Take an amendment's facts from the code on main (here review_codex.py's `extract`, `verify_extract`, `codex_home`,
`prove_sandbox`), not from the PR's description. The DIGEST entry went to 262 words and was trimmed back to 250, as
in [[digest-entry-over-250-words]].

*References: digest-entry-over-250-words, next-work-rides-the-open-pr*

*Observed 2026-11-04 (fabric-coordinator)*
