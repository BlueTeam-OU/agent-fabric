---
role: "python-dev"
class: domain
topic: "oracle-on-host-tool-binary-unstable"
description: "a test that uses a host tool (grep -i) as the oracle for a rule agrees only with that binary; assert the rule itself, and name the binary if you compare at all"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 27b8c7ca9c7d76fa
---

## a test that uses a host tool (grep -i) as the oracle for a rule agrees only with that binary; assert the rule itself, and name the binary if you compare at all

A test that pipes every code point through `grep -i` and asserts the Python regex agrees passed on my host and failed on the coordinator's: `grep` here is ugrep 7.8.4 (folds U+0130 for the i), theirs GNU grep 3.12 (also matches U+0131, and only on some regex paths). Python `re.I` alone folds both U+0130 and U+0131 into ASCII `i`; `re.I | re.ASCII` is "ASCII case only".

**Why:** an oracle that is another program's locale- and version-dependent behaviour is not an oracle for the rule, only for that binary; the old shell tool being the contract of a port does not make its folding the contract once the hooks are Python (the owner-side decision was "the name in any ASCII case").
**How to apply:** state the rule in the test (enumerate code points; match iff it is the ASCII case variant, with the allowed whitespace set listed) and keep the shell tool out of it; if a comparison against a tool is kept, record `--version` of the binary it ran against. Run a counterfactual on the unfixed pattern, and confirm the test covers every position (a draft that skipped the `i` slot passed vacuously).

*Observed 2026-10-22 (python-dev)*
