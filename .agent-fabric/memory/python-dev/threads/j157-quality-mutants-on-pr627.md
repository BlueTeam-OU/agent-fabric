---
role: "python-dev"
class: threads
topic: "j157-quality-mutants-on-pr627"
description: "j157 (j830 quality half) merged in PR #627: what landed, what was deferred, mutation and Debian ensurepip traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - bcf17513fe925460
---

## j157 (j830 quality half) merged in PR #627: what landed, what was deferred, mutation and Debian ensurepip traps

PR #627 (langid venv on the pin, with the j830 mutant-killing tests on top) MERGED on head 562b51b7: 3 work, 5 fix, 1 merge; armed on the owner's word (3 work is under the minimum of 8). The coordinator owns distribution; it was told by REPLY and INFO.

Landed: cases for arm A12/B21/B04/B07, disarm X13, arm_findings F08, post_review P12 and P19-P28/P30/P31 (size bounds inclusive), review_posters Q02, githooks_prepush pp18 (pp22 already killed, pp14's `len==4` clause equivalent); the two dead default-pin cases (test_fabric_review_cli, test_fabric_role_cli) now run on both pin shapes. B21 as worded is unreachable: the clause decides only whether git is asked about the landed head.

Deferred P3s: F3 (ADR-040 rule 4, bootstrap.py docstring, wave-9 inventory; the coordinator's job j904 on #624) and F10 (stale comment at tests/test_langid_install.py:181, mine, reword on the next commit).

**Why / how to apply:**
- A mutation survives only on committed source when a scratch-archive test runs (test_bootstrap_cli archives HEAD): commit the mutant, run, reset; back the file up to the scratchpad and cp it back.
- A fake maker for a half-made venv must act only on `-m venv`; and on a Debian slim host the pin cannot make a venv (no ensurepip), so a real-venv case must accept "{pin} -m venv failed" in the output (`assert_the_pin_made_it`) while still failing for a wrong maker. platform-smoke (debian) shows it, nothing on the dev host does.
- A review size padding is `1 + MAX - probe + 1000`, check the off-by-one with `> MAX + 1` mutants.
- A re-review base must be the checkpoint head; otherwise run a full-PR round over merge-base..HEAD. Commit trailer is `Kind: work` or `Answers:`; there is no fix-ci kind.

*Observed 2026-11-16 (python-dev)*
