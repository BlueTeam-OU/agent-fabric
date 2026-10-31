---
role: "rust-ui-dev"
class: workflow
topic: "herdr-docs-scripts-python"
description: "Before porting or rewriting a herdr file, check whether it came from upstream herdrdev/herdr — upstream's files stay as upstream wrote them (herdr#47 closed unmerged)"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "rust-ui-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - f0e64301d5131bcb
---

## Before porting or rewriting a herdr file, check whether it came from upstream herdrdev/herdr — upstream's files stay as upstream wrote them (herdr#47 closed unmerged)

herdr (agent-fabric-fleetdeck) is a fork that tracks upstream herdrdev/herdr and takes its changes as merges (docs/fleetdeck/UPSTREAM.md). The owner ruled on 2026-10-19 that a file the fork took from upstream is never ported or rewritten, because it only makes the fork diverge. agent-fabric ADR-040 rule 10 says so (agent-fabric #310, 417eb4df).

So BlueTeam-OU/agent-fabric-fleetdeck#47, which ported scripts/docs/*.mjs to Python, was closed unmerged. Those scripts were upstream's (8a6d6973). The port, oracle and review are still readable on the closed PR.

**How to apply:** before porting or reworking a herdr file, run `git log` on it. An upstream author with no `Fabric-Role:` trailer means it is upstream's; raise it with the requester rather than starting.

Testing herdr's bun suites on develop-qzapp:
- The integration fixtures tag under the account's git config, which signs tags, so run them with `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1`.
- The host has no `bun` and no `just`. Install the pinned bun 1.3.14 with npm into the scratchpad.

*Anchors: `docs/fleetdeck/UPSTREAM.md::Selective-import ledger`*

*Observed 2026-10-19 (rust-ui-dev)*
