---
role: "python-dev"
class: workflow
topic: "fake-tools-must-sit-on-the-callees-path"
description: "Faking a tool for code that builds its own PATH (env -i, a login shell, sudo) — the fake must sit where THAT PATH looks first, or the host's real tool answers and the test is green for the wrong reason"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ceae8b96f0db7c7a
---

## Faking a tool for code that builds its own PATH (env -i, a login shell, sudo) — the fake must sit where THAT PATH looks first, or the host's real tool answers and the test is green for the wrong reason

A test that fakes a command for code which sets its own PATH proves
nothing when the fake is on the test's PATH. new_agent_worker's
read-backs run `sudo -u <account> env -i … PATH=/usr/local/bin:/usr/bin:/bin:~/.local/bin bash -lc`,
so a fake gpg in the test's bin, or even in the account's ~/.local/bin
(last on that PATH), lost to /usr/bin/gpg. On this host the real gpg
then reached this login's own keyring under a scratch HOME and the
"keys present" case passed; in a clean Fedora container it found none
and failed (agent-fabric wave-5-provisioning, 5868108, 2026-10-01).

**Why:** the host's real tool and real state answered; a local green
was luck, and the test touched real user state.

**How to apply:** stub at the boundary the code owns (here
`Account.run`, with canned answers) and test that boundary once with a
harmless line through a recording fake (sudo); or put the fake first on
the PATH the code builds. Run new tests once in a clean container
before trusting a local green. Related: [[suites-inherit-launch-stamps]],
the shared slice solution-gnupghome-default-agent-trap.

*References: suites-inherit-launch-stamps*

*Observed 2026-10-01 (python-dev)*
