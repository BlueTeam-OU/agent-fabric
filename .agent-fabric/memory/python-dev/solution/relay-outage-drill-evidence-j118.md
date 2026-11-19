---
role: "python-dev"
class: solution
topic: "relay-outage-drill-evidence-j118"
description: "j118 #509 — drill evidence (shown/acks sections, parity --relay-drill); ack read-back choice, three-valued verdict, arm refusals by open review-chain findings"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 29b8d4a7fc93f854
---

## j118 #509 — drill evidence (shown/acks sections, parity --relay-drill); ack read-back choice, three-valued verdict, arm refusals by open review-chain findings

#509 merged on 3e323414 (4 work, 4 fix), armed on the owner's word. The relay has no cursor-read endpoint, so the ack is read back from `gzcoord-acks.jsonl`, one line per POST /api/ack the watch made with the relay's answer (`ok` false when refused). Verdicts are true/false/unknown; unknown never turns into failure or pass.

**Why:** an account's `skipped` for the drill files is a whole-file count repeated on every page, so use max per file then add the two files (F8/F9), never a sum over pages or one shared max.

**How to apply:**
- `fabric-pr arm` refuses while any finding of any review round in the chain is open, P3 included: a later re-review must carry a `Judgement: F<n>` line for it, or use `--defer "<head8>:F<n>" "<why>"` for a P3 that is another role's text.
- A re-review brief objective must not contain the words "fixed"/"not-fixed" (review_brief render refuses it as naming what was fixed); say "Give a Judgement line for F3".
- `tests/fixtures/ctl-usage.txt` pins the ctl usage text; regenerate when a verb's option text changes.
- GitHub 504 on the pinned-Python download and the CodeQL bundle is a flake: `gh run rerun <id> --failed`; a CodeQL run cannot be re-run, a push makes a new one.
- Do not run `gzcoord-inbox` with `&`: a detached watch is refused by `--replace`; use run_in_background.

*Anchors: `tools/fabric/control/evidence_collect.py::drill_skipped`, `tools/fabric/gzcoord/carrier/parity.py::relay_outage`*

*Observed 2026-11-08 (python-dev)*
