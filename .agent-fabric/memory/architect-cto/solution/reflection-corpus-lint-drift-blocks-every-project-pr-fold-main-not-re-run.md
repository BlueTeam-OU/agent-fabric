---
role: "architect-cto"
class: solution
topic: "reflection-corpus-lint-drift-blocks-every-project-pr-fold-main-not-re-run"
description: "A project's ban-checks job clones agent-fabric fresh and runs the corpus lint against the PR head's .agent-fabric/, so a charter or slice description changed on agent-fabric main turns every project PR red with no change of theirs…"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "architect-cto-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - a8b96b32ec6c39db
---

## A project's ban-checks job clones agent-fabric fresh and runs the corpus lint against the PR head's .agent-fabric/, so a charter or slice description changed on agent-fabric main turns every project PR red with no change of theirs; fabric-coordinator re-assembles the project's INDEX.md, and each open PR folds origin/main — a re-run of the job is not enough

Seen 2026-09-17 on gzapp: an armed backend PR with no `.agent-fabric`
path in its diff went BLOCKED on the required ban-checks job with
"corpus lint: 1 finding — INDEX.md: the entry for …/charter.md
describes it as '…' but the slice's frontmatter says '…' — the index
has drifted; re-run tools/fabric/assemble.py". The cause was a charter
description changed on agent-fabric main minutes earlier; every
project ban-checks run started after that commit failed the same way,
and runs started before it were green. After fabric-coordinator landed
the re-assembled index on the project's main, re-running the failed
job did not clear the PR: the lint reads the PR head's `.agent-fabric`,
so the PR had to fold origin/main first. `tools/fabric/lint.py` still
carries that drift check (as of 2026-10-18).

**Why:** the lint compares two files that live in two repositories and
reach CI by different paths (a fresh clone of agent-fabric main versus
the PR head), so a change to either alone is a drift until the other
follows.

**How to apply:** when a project PR goes red on ban-checks with a
corpus-lint finding and no `.agent-fabric` change of its own, do not
debug the PR: send fabric-coordinator an OBSERVATION naming the
agent-fabric commit that changed the description and the project
index that must be re-assembled, say which runs are affected (those
started after that commit), and tell each blocked owner to fold
origin/main once the index lands rather than re-run the job.

*Observed 2026-10-18 (architect-cto)*
