---
role: "python-dev"
class: solution
topic: "j55-addenda-p3-delivered"
description: "A validator's findings name the key and the expected value, never the value read; test every rewritten message on well-formed values, not only on a credential"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5401ac8b911a53e6
---

## A validator's findings name the key and the expected value, never the value read; test every rewritten message on well-formed values, not only on a credential

Branch develop-qzapp/python-dev-02/for/user/holder-addenda-p3 (head 26e56461, from origin/main 58d4d33e) holds the #290 P3s for the coordinator's stage-3 PR: no echo of a read value (role, class, agent_id, lang, extra and duplicate keys), `LINK_RE` destination stops at "]", `_decode` returns at the cap before the control scan, `hasattr(validate_set)` guards gone from test_roles_put.

**Why:** the reviewer found my first no-echo test caught only the credential-shaped values: a lowercase tag or a key name passes the shape check and was still quoted by three messages the test never reached. A linearity test is a time ratio (2000 vs 16000 repetitions, threshold 24x), not an absolute bound.

**How to apply:** for each message a change rewrites, plant the value that reaches that message (it has to pass the earlier checks) and restore the echo as the mutation. See [[j51-nonce-fence-merged]].

*References: j51-nonce-fence-merged*

*Anchors: `tools/fabric/addenda_check.py::_markdown`, `tests/test_addenda_check.py::case_a_well_formed_value_is_not_echoed_either`*

*Observed 2026-10-17 (python-dev)*
