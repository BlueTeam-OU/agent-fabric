---
role: "fabric-coordinator"
class: workflow
topic: "suite-red-on-sibling-lint"
description: "tests/run.sh red on corpus lint alone (FAILED_SUITES=1 since #624, 0 before) — lint walking sibling working copies; judge the branch with lint --no-siblings"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c720db88cfb5ffca
  - d082f684187192cb
---

## tests/run.sh red on corpus lint alone (FAILED_SUITES=1 since #624, 0 before) — lint walking sibling working copies; judge the branch with lint --no-siblings

On 2026-10-30 (j480, #433) `tests/run.sh` on develop-qzapp ended "1 suite(s) FAILED" while the python runner said
FAILED_SUITES=0: the failed one was `corpus lint`, 130 findings, all in sibling working copies under ~/projects —
gzapp's `.agent-fabric/review-card.md` at 2396 bytes (over CARD_CAP 2048, the j475 card, not yet cut there) and
INDEX drift in gzapp, herdr and agent-fabric-gateway. `AGENT_FABRIC_ROOT=$PWD python3 tools/fabric/lint.py --no-siblings`
was clean on the branch, which is what CI sees. Find the failed block by `== corpus lint` in the log, not by grepping
FAIL (fixtures print FAIL lines in passing suites). Until those siblings are fixed every local full run is red this way.
Since #624 (j830) the lint is a pool entry of the python section: a lint-only red run prints it under
`== corpus lint` and counts it, FAILED_SUITES=1, so read that block before taking the count for a failed suite;
the 0 above is how it read before #624.
Related: [[suite-verdict-not-pipeline-exit]], [[drain-fabric-project-bundle-last]].

2026-11-09 (j703): again, 113 findings, all sibling INDEX drift (interweave 42, gzapp 21, herdr 19,
agent-fabric-gateway 14, gzapi.brand 4, gzapp.decks 4, gzapi.ge 1), none in agent-fabric; the same on an
origin/main control. The siblings' INDEX.md lag the corpus: re-assembling them (tools/fabric/assemble.py) is
the drain's distribution, my lane, not a branch's defect. A `tests/test_reads_live.py: FAILED` line in the log
is test_stripped_run's fixture, not a suite ([[python-runner-names-no-failed-suite]]).

2026-11-12 (j771 → j784, #562): 94 local findings, only 15 at origin (lint.py --no-siblings
--working-copy <id>=<detached origin/HEAD worktree>, fabric at merged main 9daa89e3); InterWeave was 409
behind. The 15: brand-comms INDEX drift + a dead `domain.md` link in gzapi.brand and gzapp.decks — both
repos have my drain PRs open since 11-05/11-09 waiting on the owner's arm word (gzapi.brand#14,
gzapp.decks#29), so lint their heads before an index-only run; language-culture brief description drift
in gzapp and interweave; InterWeave's gzapi-brand-name.md city/country names (again, cf. j687) and three
over-budget threads slices (rust-ui-dev j213/j95, ux-designer j90). A dry-run `fabric-pr arm` is refused
after a session's job ended (ADR-037 rule 3); `fabric-pr gate` is allowed.

2026-11-12 (j784, fabric main 9daa89e3, every sibling at origin/HEAD): 16 findings, agent-fabric itself clean
(so j752's agent-fabric findings are gone). 8 brand-comms (gzapi.brand, gzapp.decks) lint clean at the PR heads
gzapi.brand#14 4da33ce and gzapp.decks#29 b22f32c: they go when those arm (j499/j659, j502/j660). 3 are
language-culture INDEX describing the brief by its text before d7adeb2f (gzapp, interweave, blueteam.ee):
index-only jobs j786, j785, j787. InterWeave's 5: city/country j687, over-budget splits j671. The local 94
are stale checkouts (InterWeave 409 behind, blueteam.ee 114); the one-job fence refuses even a `merge --ff-only`
of a sibling from this job's session, so each project job ffs its own checkout.

*References: drain-fabric-project-bundle-last, python-runner-names-no-failed-suite, suite-verdict-not-pipeline-exit*

*Observed 2026-11-16 (fabric-coordinator)*
