---
role: "python-dev"
class: solution
topic: "j55-addenda-p3-delivered"
description: "A validator's findings name the key and the expected value, never the value read; test every rewritten message on well-formed values, not only on a credential"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 10a1c5f3391d72c3
  - 5401ac8b911a53e6
---

## A validator's findings name the key and the expected value, never the value read; test every rewritten message on well-formed values, not only on a credential

The #290 P3s: no echo of a read value (role, class, agent_id, lang, extra and duplicate keys) in tools/fabric/addenda_check.py. Checked against origin/main 2026-10-20: `case_a_well_formed_value_is_not_echoed_either` still exists in tests/test_addenda_check.py. The linearity case no longer uses a wall-clock ratio: since 8b1de9f7 it measures CPU time (`time.process_time`), because wall time moved under host load.

**Why:** the reviewer found my first no-echo test caught only credential-shaped values: a lowercase tag or a key name passes the shape check and was still quoted by three messages the test never reached.

**How to apply:** for each message a change rewrites, plant the value that reaches that message (it has to pass the earlier checks) and restore the echo as the mutation. A linearity test is a ratio of CPU times at two sizes, never a wall-clock bound. See [[j51-nonce-fence-merged]].

*References: j51-nonce-fence-merged*

*Anchors: `tools/fabric/addenda_check.py::_markdown`, `tests/test_addenda_check.py::case_a_well_formed_value_is_not_echoed_either`*

*Observed 2026-10-20 (python-dev)*
