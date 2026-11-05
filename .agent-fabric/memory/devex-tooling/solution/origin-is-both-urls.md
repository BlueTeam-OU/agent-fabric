---
role: "devex-tooling"
class: solution
topic: "origin-is-both-urls"
description: "when checking which GitHub repo a clone's origin names (landed.origin_is), match the configured AND the insteadOf-resolved URL"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8d240474dc91270d
---

## when checking which GitHub repo a clone's origin names (landed.origin_is), match the configured AND the insteadOf-resolved URL

In agent-fabric, `tools/fabric/github/landed.origin_is` answers "is this clone's origin <owner/repo>". If it reads only the configured URL (`git config remote.origin.url`), an alias such as `gh:owner/repo` is refused. If it reads only the resolved URL (`git remote get-url`, which applies url.<x>.insteadOf), a GitHub URL routed to a mirror or a local bare repo is refused, and test_pr_gate_cli's fixture routes origin exactly that way. So it matches either one (commit da5f86b8, j151, review of #300 round 2).

Every gate path that reads the cwd clone under `--repo` has to check origin_is: first the commit count (j146), then `--in-flight`/`--overlap` (ecffbd23). A new path that reads origin refs needs the same guard.

A new refusal in a gate path is said in three places, or a review finds the gap (#304 F3, fece8925): `fabric_pr.py`'s --repo help, `pr_gate.py`'s module CONTRACT exit line, and its Usage example. test_pr_gate_cli checks the help.

*Anchors: `tools/fabric/github/landed.py::def origin_is`, `tools/fabric/github/pr_in_flight.py::landed.origin_is`*

*Observed 2026-10-18 (devex-tooling)*
