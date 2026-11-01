---
role: "python-dev"
class: threads
topic: "j94-interweave-evidence-merged"
description: "j94 — interweave-evidence op + parity --collected merged (#390, 04d3b2cc); traps for the next control-op PR"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 14a5c638839b2c8b
---

## j94 — interweave-evidence op + parity --collected merged (#390, 04d3b2cc); traps for the next control-op PR

j94 done 2026-10-26: PR #390 merged as 04d3b2cc (2 work, 6 fix, 1 merge). Signed read op `<carrier>-evidence` (carrier_evidence.py account side, evidence_collect.py paging/filing, ctl.py verb, parity.py `--collected`); the coordinator supplied the ADR-029/ADR-064 text on my branch (fold, then re-review each head) and folded main when ADR files conflicted.

**Traps:** (1) a new ctl verb must add no key to `parse_args` output or `rows()` rows for other verbs: test_control_frozen holds both against an oracle fixture, CI-only red. (2) A full `tests/run.sh python` under `env -i` on this host can drown in ENOSPC and 900 s budgets; judge by the touched suites in a stripped copy. (3) `fabric-review next` needs card_base and full ids in the request; a comment-only fix still needs a review of the new head (the gate counts the head). (4) My session is not a host operator: a signed op returns "not a host operator" from here, so a live run needs the coordinator's session; ask for it early. (5) post-review rounds: `fabric-review save PR N < report` after each post, then `next`.

**Why:** owner put ADR-064 steps at maximum priority. See [[j92-rule13-carrier-live-check-state]].
**How to apply:** the next control op follows the same split: account-side module, collector, thin ctl verb, frozen-shape check first.

*References: j92-rule13-carrier-live-check-state*

*Observed 2026-10-26 (python-dev)*
