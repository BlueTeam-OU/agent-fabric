# ADR-065 — amendments

The full notes; the ADR's body reads current and its Amendments table lists them.

### Amendment 2026-10-31 — A full review carries the findings earlier chains left open

#425 merged with F5 open. An earlier review chain raised it, nothing judged it, and a fresh full review of the head started a chain of its own, which the review gate read as "head reviewed". Gate 4c of `fabric-pr arm` now refuses on a finding open in any chain (`tools/fabric/github/arm_findings.py`, #437). That closes the merge, but the next full review still did not know the finding existed, so the PR could only be armed by a re-review on the old chain or a `--defer`.

A PR's full-review brief now reads the PR's reviews with the same reader and from the same accounts (the PR's author and `AGENT_FABRIC_REVIEW_POSTERS`), and lists each open finding with its label, level, place and the head it was raised on, for the reviewer to answer in a `Judgement:` line. The reviewer numbers its own findings past every label the PR's reviews used, closed ones included. A judgement goes to its own chain whenever that chain raised the label, so a new F5 would take the judgement meant for the old one. A finding raised on the head under review is another engine's same round, and blind review (ADR-020) keeps it out; its label still counts. Reviews that cannot be listed refuse the render, since rendering them as none is the gap this closes. The Codex engine is handed none: its answer carries findings only and its renderer numbers them from F1, which a follow-up of its own changes.
