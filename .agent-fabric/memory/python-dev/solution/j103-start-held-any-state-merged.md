---
role: "python-dev"
class: solution
topic: "j103-start-held-any-state-merged"
description: "j103 #434 merged; start refuses under a hold in any state; re-review brief needs card_base, post-review needs a report file with the dispatch header"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 53b2f8a09324a559
---

## j103 #434 merged; start refuses under a hold in any state; re-review brief needs card_base, post-review needs a report file with the dispatch header

#434 merged (verbs.py change() start: `if held:`, jobs.py help text). Import deliberately unchecked; its held test lives in tests/test_jobs_transfer.py (subprocess, hold set via identity.set_hold in a state dir), not test_jobs_switch (in-process export fails on sys.stdout.buffer).

**Why:** ADR-037 rule 13 amended in #433 (user's PR, unmerged then); ADR text is outside my entry, so the comment cites #433.
**How to apply:** fabric-review brief takes a JSON with `repository` as a working-copy path; a re-review whose base is a PR commit needs `card_base` = first round's base. post-review wants the brief's dispatch header block first, so write the subagent's report to a file and prepend it. Commit commands containing $HOME are refused by the job-copy guard; run the suite in its own command. arm minimum in agent-fabric was 1 work commit.

*Observed 2026-10-30 (python-dev)*
