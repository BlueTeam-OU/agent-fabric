---
role: "python-dev"
class: workflow
topic: "trailer-block-must-be-one-line-per-key"
description: "before writing a commit message with Answers:/Fabric-Role: trailers — a wrapped trailer value hides Fabric-Role from git, and the authority guard fails"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-10"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 4a48f00778e18ccc
---

## before writing a commit message with Answers:/Fabric-Role: trailers — a wrapped trailer value hides Fabric-Role from git, and the authority guard fails

On 2026-10-07 commit 2fe3cfb2 on actions-health-fields ended with:

    Answers: GZCoord REQUEST <id> (devex-tooling; status
    "operational" on the healthy answer per its REPLY <id>)
    Fabric-Role: python-dev

The wrapped second line is not a `Key: value` line, so git no longer
reads the block as trailers. `%(trailers:key=Fabric-Role)` came back
empty, and check_agent_fabric_dir_authority said "[Fabric-Role: none]".
The commit-msg hook did not catch it; only the full suite did.

**Why:** a suite run is spent on a message, and the branch has to be
rewritten before it is pushed.
**How to apply:** keep every trailer on one line, and put the prose in
the body above the blank line. After committing, run
`git log --format='%h %(trailers:key=Fabric-Role,valueonly)' <base>..HEAD`.
To fix an unpushed commit, work on the contributor branch itself: an
amend, or a scratch branch, is refused by the pre-commit hook ("no path
staged" / "not a contributor branch"). Use `git reset --hard <base>`,
then `git cherry-pick -n <commit>`, then `git commit -F msg`, then
cherry-pick the rest, and check the tree with `git diff --quiet <old> HEAD`.

*Observed 2026-10-07 (python-dev)*
