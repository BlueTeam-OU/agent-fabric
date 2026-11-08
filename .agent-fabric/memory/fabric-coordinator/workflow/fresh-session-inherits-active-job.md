---
role: "fabric-coordinator"
class: workflow
topic: "fresh-session-inherits-active-job"
description: "a fresh session launched for job B can start with job A still active and A's branch ahead of origin; the push guard then refuses from the agent-fabric cwd, so leaving A means dropping a re-creatable merge, not pushing"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-08"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 098db945d7ac304a
  - b6e7d1d500d8a072
---

## a fresh session launched for job B can start with job A still active and A's branch ahead of origin; the push guard then refuses from the agent-fabric cwd, so leaving A means dropping a re-creatable merge, not pushing

2026-11-03: the session launched for j562 found j502 (gzapp.decks drain) still active, its branch one unpushed
merge of origin/main ahead. `fabric-jobs switch j562` refused (j502 active), and after a pause it refused again
(unpushed commits, memory unchanged). The push itself was refused by the job guard twice: once with no active job
("this session worked j502"), and again after re-activating j502, because the session cwd is agent-fabric, not
j502's copy ([[guard-counts-session-cwd]]). The way out was `git reset --keep` to the origin branch. That is safe only
because the only extra commit was a merge of main that can be redone with one command. Look at
`git log origin/<branch>..HEAD --not origin/main` first. If it shows real work, run `fabric-fresh --job <A>` and push
from there instead.
Related: [[switch-to-named-job-directly]], [[block-active-job-locks-session]].

2026-11-07, again (j631 named, j577 active at launch, same copy): pause j577 + start j631 worked, but the publish
guard still refused `fabric-pr post-review` — the session counts as having worked the job active at launch. So when
the launch's active job is not the one the start message names, do nothing that publishes: pause the named job's
predecessor, `fabric-jobs switch`, and run the `fabric-fresh --job` it prints straight away.

*References: block-active-job-locks-session, guard-counts-session-cwd, switch-to-named-job-directly*

*Anchors: `tools/fabric/jobs.py::switch`*

*Observed 2026-11-03 (fabric-coordinator)*
