---
role: "python-dev"
class: workflow
topic: "stripped-fixes-merged-in-138"
description: "#138 (merged 2026-10-09) fixed 14 test files on a stripped copy; the traps: token routes, no-origin copy, claude absent on CI, fixture vs live distinctness"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - dc84716e3361eea1
---

## #138 (merged 2026-10-09) fixed 14 test files on a stripped copy; the traps: token routes, no-origin copy, claude absent on CI, fixture vs live distinctness

PR #138 merged (12 work, 6 fix, 6fc601d3): j74, j75 and the coordinator's test_control_queue observation.

- A "no token" case must isolate every route of tokens.py: synced secrets.env (HOME), env var, the cwd's git toplevel
  `.claude/settings.local.json` (chdir to a non-repo temp dir), and `<dirname(AGENT_FABRIC_ROOT)>/.gzcoord/bridge-token`
  (the hosting account has one). Plant a decoy at ~/projects/.gzcoord/bridge-token to reproduce; remove it after.
- A stripped copy is a one-commit repo with no `origin`: `gh.this_repo()` fails; name the repo with GH_REPO in the test.
  stripped_run now fetches the tree's history so a port's oracle (`git show <old sha>:file`) reads; old commits hold
  instance data, so no test may read it through git.
- A CI runner has no `claude`: user-settings.py writes autoMode only when `claude auto-mode defaults` answers
  (AGENT_FABRIC_CLAUDE stand-in). An assertion that passes on an account with claude can fail on every CI leg.
- Review rule: a fixture must hold a name/value the live data lacks, proven by pointing the reader back at live data
  (relay_catchup/episodic fixtures first used the live ids and channel: a P2).
- status.py takes its root from its own realpath: a status test needs real copies of bin/ and tools/, not links.
- fill-then-send: `compose && python fill && send` chained with `;` sent an EMPTY INFO when the fill raised (seq 34103);
  chain with && so a failed fill stops the send.
- js.py "3.12 (CI)" comment stays until the coordinator's CI change drops the 3.12 matrix entry.
Related: [[stripped-run-and-the-nightly-skip-list]], [[chain-message-fill-to-send]].

*References: chain-message-fill-to-send, stripped-run-and-the-nightly-skip-list*

*Observed 2026-10-09 (python-dev)*
