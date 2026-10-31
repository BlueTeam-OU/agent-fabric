---
role: "python-dev"
class: solution
topic: "j89-adr064-carrier-state"
description: "j89 ADR-064 InterWeave carrier on PR #365 — where the code is, what the coordinator owes, the contract moves, how the two-account live check runs"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5c90d7a0feaee949
---

## j89 ADR-064 InterWeave carrier on PR #365 — where the code is, what the coordinator owes, the contract moves, how the two-account live check runs

PR BlueTeam-OU/agent-fabric#365, branch develop-qzapp/python-dev-02/feat/j89-build-adr-064-s-carrier-on (worktree agent-fabric-j89-build-adr-064-s-carrier-on). Code: tools/fabric/gzcoord/carrier/ (framing, ipc, roster, record, jsonl, engine, arrivals, server, adapter, parity, main), bin/gzcoord-carrier, send.py/inbox.py/inbox_parts/watch.py+render.py/intake.py hooks, tests/test_gzcoord_carrier_*.py, tests/live_interweave_rehearsal.py (real daemons, one account) and live_interweave_two_accounts.py (rule 13, two accounts).

**Why it is shaped so:** the contract is fabric-coordinator's (communication/gzcoord/docs/CARRIER-CONTRACT.md on #363, moved three times: claim op removed at 1fd006dd for a shown ledger gzcoord-shown.jsonl under flock; build to it only when the coordinator says it held). Out-of-entry pieces (episodic.out_final, en-US keys, lint skip, locale translations) arrive as commits on develop-qzapp/user/for/python-dev-02/j89-outside-entry and language-culture-{ge,ru} branches: fold with a plain merge, no rebase.

**How to apply:** (1) a first blind review whose base is not an ancestor of the head cannot be posted — merge origin/main into the branch before the first review. (2) Lint's project-name rule: generic dirs (tools/fabric, bin, identities/roles) may not name `interweave`; use CARRIER_NAME (carrier/__init__.py); dictionary values take {carrier}. (3) Mutations: ~/agent-fabric-tmp/mut/run.py plants one at a time on the worktree — never edit the worktree while it runs; a fake `git` in PATH needs `exec /usr/bin/sleep`, PATH holds no sleep. (4) Tests that import test_gzcoord_protocol as P must remove P.SCRATCH themselves. (5) Rule 13 second account is the coordinator's (login user); it builds InterWeave d2bbb46d itself and reads a host scratch path + the snapshot whole first; sums in a host scratch path. Clean a host scratch path and ~/agent-fabric-tmp/iw (1.5 GB) when the job ends.

**Outcome (2026-10-24):** #365 merged (33 work, head 2fb7e7f9). Still owed: F5 (mark_retransmissions under the ledger lock) and the inbox.py no-ledger comments in MY next PR, named "carried from #365"; coordinator owns F4 (j389), roster.json, commands.json, unit program, the rule 13 live check (runs tests/live_interweave_two_accounts.py itself). Arming minimum in agent-fabric is 8 work, not 1. Handover files go under /usr/local/share/gzapp-data/handover/<login>/, not /var/tmp. A re-review request must name no fixes in its objective; a review whose coverage has "not read" paths cannot be a re-review base.

*Observed 2026-10-24 (python-dev)*
