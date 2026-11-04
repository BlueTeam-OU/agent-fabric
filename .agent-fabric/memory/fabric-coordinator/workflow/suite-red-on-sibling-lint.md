---
role: "fabric-coordinator"
class: workflow
topic: "suite-red-on-sibling-lint"
description: "tests/run.sh \"1 suite(s) FAILED\" with FAILED_SUITES=0 — corpus lint walking sibling working copies; judge the branch with lint --no-siblings"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c720db88cfb5ffca
---

## tests/run.sh "1 suite(s) FAILED" with FAILED_SUITES=0 — corpus lint walking sibling working copies; judge the branch with lint --no-siblings

On 2026-10-30 (j480, #433) `tests/run.sh` on develop-qzapp ended "1 suite(s) FAILED" while the python runner said
FAILED_SUITES=0: the failed one was `corpus lint`, 130 findings, all in sibling working copies under ~/projects —
gzapp's `.agent-fabric/review-card.md` at 2396 bytes (over CARD_CAP 2048, the j475 card, not yet cut there) and
INDEX drift in gzapp, herdr and agent-fabric-gateway. `AGENT_FABRIC_ROOT=$PWD python3 tools/fabric/lint.py --no-siblings`
was clean on the branch, which is what CI sees. Find the failed block by `== corpus lint` in the log, not by grepping
FAIL (fixtures print FAIL lines in passing suites). Until those siblings are fixed every local full run is red this way.
Related: [[suite-verdict-not-pipeline-exit]], [[drain-fabric-project-bundle-last]].

*References: drain-fabric-project-bundle-last, suite-verdict-not-pipeline-exit*

*Observed 2026-10-30 (fabric-coordinator)*
