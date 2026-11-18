---
role: "python-dev"
class: solution
topic: "j133-compose-authorizes-state"
description: "j133 merged as #540 — compose --authorizes (once), send warning after the post; review F1, traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8f11a3c7cc89679b
---

## j133 merged as #540 — compose --authorizes (once), send warning after the post; review F1, traps

#540 merged (7 work, 1 fix), head a91beee8: `gzcoord-compose --authorizes <owner>/<repo>#<n>@<sha>`, given once (a header key has one value; arm reads one), checked with `github.arm.WAIVES`, DECISION/REPLY with `--to` only. `gzcoord-send` warns (key `send.authorizes-in-body`) after the post.

**Why:** blind review F1 (P2): the coordinator-worded en-US line says "this message was sent", so printing it right after validation contradicted a dry run or refusal. Carried unproven: no warning when only a mirror carrier delivered; new warning sub-cases do not pin exit codes.

**How to apply:** a dictionary line outside my entry arrives by REPLY from the coordinator (next session) and the locale holders (for/ branches to cherry-pick); its wording may change my code's placement, so write tests against the key, not the text. Re-review request: leave `previous_findings` out (the tool reads the last posted review); `fabric-pr post-review` must be a bare command. A wait loop grepping `^exit ` matches test text "exit codes": match `^exit [0-9]+$`. `test_review_codex` flaked once under the full run and once alone, green after. See [[commit-kind-trailer]].

*References: commit-kind-trailer*

*Anchors: `tools/fabric/gzcoord/compose.py::check_authorizes`, `tools/fabric/gzcoord/send.py::grant_in_body`*

*Observed 2026-11-10 (python-dev)*
