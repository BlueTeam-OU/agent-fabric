---
role: "fabric-coordinator"
class: rationale
topic: "never-list-supply-tier"
description: "owner 2026-11-07 approved splitting CONTRIBUTOR_NEVER into a hard fence and a supply tier contributors commit on for/<coordinator> branches only"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - af0b3bc9d3973454
---

## owner 2026-11-07 approved splitting CONTRIBUTOR_NEVER into a hard fence and a supply tier contributors commit on for/<coordinator> branches only

Owner 2026-11-07, asked "review that list, likely a bit too strict", chose the supply tier
over "keep as is" and over "contributors merge it themselves".

- **Hard** (never a contributor's commit): what judges a contributor's own commit or its
  review — tools/fabric/guards/, git.py, lint.py + lint_rules/ + what lint loads by path
  (layout, workingcopy, adr), the suite runners, the authority tests, review_brief/card/
  rounds + bin/fabric-review, the review/dispatch fence hooks, managed_settings, the
  carrier fence, github-host-keys; and the definitions (identities/, routing/, policies/,
  protocol, docs/adr/, memory/, .agent-fabric/, .github/, AGENTS.md, CLAUDE.md).
- **Supply**: a contributor commits only on `<host>/<login>/for/<coordinator>/<what>`;
  the coordinator folds, the blind review covers it, the coordinator arms and merges.
  Non-guard hooks in runtime/claude-code/hooks (listed file by file), launch_prompt.py,
  bootstrap.py, fabric_writes, install_agent_files, workspace_trust, episodic*, relay*,
  history, reflect, relay_catchup, python_pin + runtime/python.json.
- **Moved back to hard after the approval, by the same rule** (said to the owner):
  identity.py (commit_hooks.py runs `identity.py --role` to decide the binding),
  role.py + bin/fabric-role (writes that binding), routing.py (tests/run.py and
  dispatch_guard run it), fabric_settings.py (lint_rules/schema.py loads it by path).
  Check "does a guard, lint or a runner load or run it" before moving any path.

Why: before this, delegating into the list meant hand-applied patches (j319, j334);
28k of 261k code lines, 133 files, were fenced. #497 had merged before the work began,
so it landed as its own PR: BlueTeam-OU/agent-fabric#501 (j630, ADR-018 A 2026-11-07), merged 2026-11-07 as
d2b23006 (9 work, 5 fix) and distributed to all 30 accounts.

How it is built (#501): `supplies` admits its paths whatever `paths`/`excluding`/`merges`
say — an entry keeps a supply path excluded from `paths` and names it again; the keyboard
wants for/<a role_definitions holder>/, CI wants an owner-role commit in the PR.
lint: CONTRIBUTOR_NEVER keeps runtime/claude-code/ whole; CONTRIBUTOR_SUPPLY carves
14 workspace hooks out file by file, so a new hook is hard until listed. Every hook in
runtime/claude-code/managed/hook_entry.py GUARDS, hook_jq.py and session-seal.py
(self-kill-guard loads it) stay hard; test_lint enforces it. Left open: tools/fabric/plan_hold.py
is a managed-settings hook yet unfenced in python-dev's tools/ (it never refuses).
Related: [[delegate-to-subagents]], [[fence-exclusion-held-by-lint]].

*References: delegate-to-subagents, fence-exclusion-held-by-lint*

*Observed 2026-11-07 (fabric-coordinator)*
