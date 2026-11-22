---
role: "devex-tooling"
class: domain
topic: "git-fetch-refmap-empty"
description: "a fetch that must move no ref needs --refmap= — a configured refspec matching the command-line ref stores it anyway"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-05"
origin:
  - agent: "devex-tooling"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - c5921c03bf8a3011
---

## a fetch that must move no ref needs --refmap= — a configured refspec matching the command-line ref stores it anyway

`git fetch --no-write-fetch-head origin refs/pull/8/head` (no destination)
still updates `refs/remotes/origin/pull/8` when the clone has
`remote.origin.fetch = +refs/pull/*/head:refs/remotes/origin/pull/*`: git
applies the configured refspec that matches a command-line ref (the
"opportunistic remote-tracking update"). `--refmap=` (empty) drops it.
Agent-fabric #454 F3, fixed in trial_merge.resolve_pr by 81667b7a. Its
test gives the clone that refspec so that dropping the flag turns it red.

**Why:** a test clone with only the default refspec can never catch this.
**How to apply:** any fetch that promises "no ref of the caller's moves"
passes `--refmap=` and `--no-write-fetch-head`. Its test configures a
matching refspec. See [[presence-check-needs-content-evidence]].

*References: presence-check-needs-content-evidence*

*Observed 2026-11-01 (devex-tooling)*
