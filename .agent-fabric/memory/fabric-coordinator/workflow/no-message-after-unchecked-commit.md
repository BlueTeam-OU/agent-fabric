---
role: "fabric-coordinator"
class: workflow
topic: "no-message-after-unchecked-commit"
description: "Never put a gzcoord-send naming a commit in the same command as the commit unless it runs only on the commit's success and after the remote reads back"
tier: 1
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: user
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7b7867d15a5f2dac
---

## Never put a gzcoord-send naming a commit in the same command as the commit unless it runs only on the commit's success and after the remote reads back

2026-10-25, #385: I committed an ADR amendment onto python-dev-01's branch, pushed and sent a REPLY
naming "the commit" all in one `;`-separated command. The ADR pre-commit hook refused the commit, the
chain went on, and the REPLY named the branch's existing head as my commit. I had to send a correction
(01a17520-7d5a) before the right REPLY (01a17522-c5de).

**Why:** a REPLY naming an artifact is an acknowledgement others act on (request a re-review, arm); a
false one costs the recipient a round and trust.
**How to apply:** commit in its own call and read `rc`; push in its own call and read back
`git ls-remote` against `git rev-parse HEAD`; only then compose the message with that id. Related:
[[verify-sends-in-journal]], [[supply-contract-commit-and-push]].

*References: supply-contract-commit-and-push, verify-sends-in-journal*

*Anchors: `bin/gzcoord-send::gzcoord-send`*

*Observed 2026-10-25 (fabric-coordinator)*
