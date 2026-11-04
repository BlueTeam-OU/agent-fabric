---
role: "devex-tooling"
class: solution
topic: "arming-mode-no-ci"
description: "choosing a repos/<repo>.json mode for a repository with no CI, and what \"direct\" really allows"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 888366687a8fae1e
---

## choosing a repos/<repo>.json mode for a repository with no CI, and what "direct" really allows

In the arming schema, `direct` means no ruleset at all: arm_policy.render returns ruleset None, so GitHub allows a push straight to main and the pre-push hook is the only fence. It does not mean "PRs, without a merge queue". A repository whose README says "every change is a pull request" therefore cannot be `direct`. fabric-coordinator corrected exactly that on blueteam.brand (REPLY 01a1519e, 2026-10-19, j152).

With no CI, every PR-requiring mode has a catch:
- `auto` with required_checks [] makes arm (arm.py, around the "none-yet" branch) wait for every check on the head to be green. With no CI that reads none-yet and refuses every PR; the no-check exception is direct's alone.
- `owner-only` gets the pull_request ruleset, and arm refuses, so the owner merges by hand.

The schema says auto/queue need at least one required check, but the settings validator does not enforce it ([redacted]-shop-transit is auto with []).

Decided for blueteam.brand (REPLY 01a151a1): owner-only until a CI check exists, then auto with that check (import step 7). Widening the no-CI exception to auto is not wanted: it stays direct's alone.

j253 (2026-10-30), after [redacted]-shop-transit#2 had to be hand-merged (OBSERVATION 01a1816c): the gap is closed per PR, not by mode. A separate basis phrase, "owner's no-CI word", lifts only the checks gate. It applies in PR mode with required_checks [], a none-yet head, a base with no .github/workflows (the read must answer 404) and a PR that adds no workflow. The count's "owner's word" never lifts the checks gate, and the no-CI word never lifts the count gate. The contract went to python-dev-01 as REQUEST 01a18b19; it was delivered as BlueTeam-OU/agent-fabric#424 (owner review accepted at 2079420b), and the decision to fabric-coordinator as REPLY 01a18b19-a542. #424 merged on 2026-10-30, so the phrase is live. A sentence for policies/pull-requests/SKILL.md was proposed to fabric-coordinator in REPLY 01a18ca9.

*Anchors: `tools/fabric/github/arm_policy.py::if p["mode"] == "direct":`, `tools/fabric/github/arm.py::checks == "none-yet"`*

*Observed 2026-10-30 (devex-tooling)*
