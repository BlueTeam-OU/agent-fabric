---
role: "python-dev"
class: workflow
topic: "j70-githook-oracles-merged"
description: "j70 (#321 merged) — githook and model-fallback-note oracles already had overrides; what was added, mutation-run recipe, review/suite traps"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - d6b870ebc35c7a4a
---

## j70 (#321 merged) — githook and model-fallback-note oracles already had overrides; what was added, mutation-run recipe, review/suite traps

#321 merged 2026-10-19 (1 work, 1 fix): tests/ only. The oracles of Wave 9 batches 4 and 6 already carried their override (`$MODEL_FALLBACK_HOOK` via hook_harness.entry; `$GITHOOKS_DIR` via githook_fixtures) — audit before adding.

**Why:** a request asking to "add the override" may already be satisfied by an earlier commit (4e3edec1); the value is the audit of what each hook decides against the cases.

**How to apply:**
- Mutation runs: copy policies/githooks to the scratchpad, sed one line, run the test with GITHOOKS_DIR=<copy>; a mutation that kills some other test is not proof for the new case — a negative case needs the state where the mutated behaviour would visibly refuse (review F1: "not checked" case passed silently on consistent records).
- A passing check is silent: "not checked" cases need pre-broken state.
- Full tests/run.sh takes 35+ min on this host and flakes at load >70 (gzcoord inbox --follow case); background waiters are cut at 30 min — wait on the rc line in the log, not a long until-loop with default timeout.
- fabric-review brief: mode `review`/`re-review`, repository = worktree path, previous_findings = a file path, card_base = round-one base sha.

*Observed 2026-10-19 (python-dev)*
