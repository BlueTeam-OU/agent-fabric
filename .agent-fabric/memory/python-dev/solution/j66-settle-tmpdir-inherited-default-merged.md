---
role: "python-dev"
class: solution
topic: "j66-settle-tmpdir-inherited-default-merged"
description: "#311 merged — settle_tmpdir drops this login's pre-#292 /var/tmp TMPDIR; why restarts kept it, security-boundary arm, review traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 5e6249589928defd
---

## #311 merged — settle_tmpdir drops this login's pre-#292 /var/tmp TMPDIR; why restarts kept it, security-boundary arm, review traps

A restarted session keeps the environment of the long-lived launcher
process (`tools/fabric/launch.py`, via moveto) it descends from: one
born before #292 (2026-10-17 23:18Z) carried TMPDIR=/var/tmp/agent-fabric-<login>
and `settle_tmpdir` treated it as the account's own, so no restart moved
it. #311 (merged 2026-10-19 on the owner's word) makes
`tools/fabric/launcher/session.py settle_tmpdir` treat exactly
`/var/tmp/agent-fabric-<this login>` as unset (`legacy_tmpdir`, `login=`
keyword, default from `pwd.getpwuid(geteuid())`, KeyError → keep value).
Found by tracing /proc/<pid>/environ up the ancestors.

**Why:** the 40G /var/tmp root volume filled on 2026-10-17.
**How to apply:** session.py is a security-boundary file: under 8 work
commits it arms only on the owner's word. A re-review of a fix range
needs `card_base: <first round's base sha>` in the request. Helpers live
in ~/.local/share/agent-fabric-python-dev/ (~/agent-fabric-tmp is pruned
weekly). Live proof is a fresh launch after `fabric-ctl all upgrade fabric`;
then remove /var/tmp/agent-fabric-python-dev-02 (j65). See [[ci-env-for-lint-and-mutations]].

*References: ci-env-for-lint-and-mutations*

*Observed 2026-10-19 (python-dev)*
