---
role: "python-dev"
class: domain
topic: "no-token-case-needs-root-and-ceiling"
description: "a \"no token\" test needs a scratch cwd AND a scratch AGENT_FABRIC_ROOT AND a git ceiling; cwd alone leaves the workspace bridge-token"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 65670391e8f6f325
---

## a "no token" test needs a scratch cwd AND a scratch AGENT_FABRIC_ROOT AND a git ceiling; cwd alone leaves the workspace bridge-token

gzcoord's `_token()` walks synced secrets, env, token_env_file, `<git toplevel of cwd>/.claude/settings.local.json`, then `<dirname(fabric_root)>/.gzcoord/bridge-token`. A scratch cwd cuts only the fourth source; the last comes from the fabric root, so the case also sets `AGENT_FABRIC_ROOT` to a scratch path, and `GIT_CEILING_DIRECTORIES=dirname(cwd)` keeps a TMPDIR inside a checkout from resolving into it (test_control_agentd, #270; same shape as j76).

**Why:** the case passed in CI and on accounts without a relay host's bridge-token, and failed only on the relay host; this account has no such file, so prove it in a scratch copy with `ws/.gzcoord/bridge-token` planted beside the checkout, old case red, new green.
**How to apply:** for any test meaning "no token/secret", list every source the lookup walks and cut each; plant each one as a counterfactual. See [[suites-inherit-launch-stamps]].

*References: suites-inherit-launch-stamps*

*Observed 2026-10-15 (python-dev)*
