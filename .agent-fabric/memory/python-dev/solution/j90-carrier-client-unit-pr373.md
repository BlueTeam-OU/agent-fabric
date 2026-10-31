---
role: "python-dev"
class: solution
topic: "j90-carrier-client-unit-pr373"
description: "j90 PR #373 — carrier client unit program, installer, worker step 7b, roster schema; patches 3-4 delivered; what waits on the owner"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8f5cc33f6fda8f70
---

## j90 PR #373 — carrier client unit program, installer, worker step 7b, roster schema; patches 3-4 delivered; what waits on the owner

PR BlueTeam-OU/agent-fabric#373, branch develop-qzapp/python-dev-02/feat/j90-j379-the-carrier-s-deployment-after (worktree agent-fabric-j90-…). Code: runtime/interweave/client (bash), tools/fabric/gzcoord/carrier/install_client.py (in the carrier dir because lint refuses the project name in generic dirs), worker.py step 7b `install_client`, `gzcoord-carrier run --profile P`, runtime/interweave/roster.schema.json + tests/test_interweave_*.py. Patches for commands.json / live-check / CARRIER-CONTRACT went to /usr/local/share/gzapp-data/handover/python-dev-02/ and the coordinator accepted them (landing on their #371).

**Status 2026-10-25:** #373 MERGED (4 work, 2 fix). My own arm attempt was refused by the auto-mode classifier because the owner's word reached me only as agent relays; it merged anyway once someone with standing armed it. Coordinator's patches landed on #371 (6bf72ab0). Rule 13's two-account run is the coordinator's and waits on an InterWeave v* tag; a REQUEST for the carrier half may follow.

**Why it mattered:** head 64565df0 was green and reviewed; below the arming minimum, so the owner's word armed it. Rule 13's two-account run (coordinator, j378) waits on the merge and on new-agent/installer run per account.

**How to apply:** (1) run `tests/static.sh` (ruff + shellcheck, repo scripts must be bash) before every commit — CI static went red twice on a sh shebang and an unused variable. (2) Any change to worker.finish step order breaks test_ssh_add_login and test_launch_record order tests and the new_agent_cli fixture (copy the files the step runs into the fixture clone). (3) A mutation that removes the --profile check makes the process test hang (a real carrier starts): kill by pid, restore from a copy — never `git checkout` inside the same chained command. (4) Handover patches: `git add -N`, `git diff -- path`, then reset/checkout.

*Anchors: `tools/fabric/gzcoord/carrier/install_client.py::def install`, `tools/fabric/provisioning/worker.py::def install_client`, `runtime/interweave/client::gzcoord-carrier`*

*Observed 2026-10-24 (python-dev)*
