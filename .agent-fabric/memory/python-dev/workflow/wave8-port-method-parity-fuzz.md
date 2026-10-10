---
role: "python-dev"
class: workflow
topic: "wave8-port-method-parity-fuzz"
description: "how the Wave 8 control-plane ports (upgrade.py #146, ctl.py #149) were proved: Node tests ported, parity cases, fuzz with lenient_node_throw, mutation passes, CodeQL flows read from SARIF"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-03"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 085b651f2cf56647
---

## how the Wave 8 control-plane ports (upgrade.py #146, ctl.py #149) were proved: Node tests ported, parity cases, fuzz with lenient_node_throw, mutation passes, CodeQL flows read from SARIF

Method that worked for #146/#149 (python-dev-03, 2026-10-09):
- Port the .mjs tests case for case (command cases as a subprocess against a Python fake relay, real gpg/git/fabric-lease where the Node used them), then parity cases in `tests/parity_cases_<module>.py` through `tests/test_control_parity.py`.
- For text built from untrusted replies, one parity case replaces each field of every reply (scalars AND containers) with another kind and compares sha256 of the table; `lenient_node_throw: True` in the case skips elements where the Node throws (a Node TypeError is no contract). Run a scratch copy returning the tables to read diffs. It found real differences each round (toFixed sign, JS `+` on strings, in-place sort, join of null, mkdir mode of parents, Buffer base64 leniency).
- Mutation pass in the background (a script editing the source, running the unit tests, restoring): survivors get a case; equivalent mutants are named in the PR body.
- Blind review before pushing fixes; post each review BEFORE the push that answers it, then re-review the fix range; `fabric-review brief` takes `previous_findings` as a FILE path.
- CodeQL alert flows: `gh api -H "Accept: application/sarif+json" repos/<o>/<r>/code-scanning/analyses/<id>` has codeFlows; dismiss false positives with a comment under 280 characters.
**Why:** each round of the reviewer found what the corpus did not cover; the SARIF read took minutes instead of guessing.
**How to apply:** a port of untrusted-text code in this repo; see [[tools-report-and-pr-lessons]] for the PR mechanics.

*References: tools-report-and-pr-lessons*

*Observed 2026-10-09 (python-dev)*
