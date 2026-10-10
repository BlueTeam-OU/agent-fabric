---
role: "fabric-coordinator"
class: workflow
topic: "check-detail-never-a-value"
description: "A test's failure detail prints what it compared; a check about secrets compares set/unset per name in a clean env, never values"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 995e8fe26b3655e7
---

## A test's failure detail prints what it compared; a check about secrets compares set/unset per name in a clean env, never values

A secrets test that spawns a shell inherits the runner's environment, and a
session's environment holds the real secrets. On 2026-10-06 a new
test_secrets_sync check ran `bash -ic 'printf $GH_TOKEN'` with
`{**os.environ, HOME: tmp}`; it failed, and `check(..., detail)` printed the
owner's real GitHub token and this login's OpenRouter key into the session.

**Why:** the failure path is exactly when the detail is printed, and an
inherited env makes the "should be unset" value the real one.

**How to apply:** in any check about credentials: build the child env from
scratch (HOME, PATH, TERM only), ask the shell for `NAME=set|unset`, and
pass only that as the detail. The same for a real tool (gh) in a test: point
it at a fake (AGENT_FABRIC_GH, tests/fixtures/fake-gh-auth.sh); gh follows
XDG_CONFIG_HOME and the keyring, not HOME. See [[gnupghome-default-agent-trap]].

*References: gnupghome-default-agent-trap*

*Observed 2026-10-06 (fabric-coordinator)*
