---
role: "python-dev"
class: solution
topic: "j225-subagent-effort-merged-550"
description: "j225 (#550) refused CLAUDE_CODE_SUBAGENT_EFFORT like the effort level; fence list sites, review/mutation traps"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 7fb922b4101f9118
---

## j225 (#550) refused CLAUDE_CODE_SUBAGENT_EFFORT like the effort level; fence list sites, review/mutation traps

#550 merged 2026-11-10 (1 work, 1 fix, armed at min 1 on the owner's word after a green suite). The variable is named in five places that must agree: settings.py scan + process-env refusal, launch.py docstrings, model_audit.py (`PRINTED` and `of_interest`), status.py `present`, and the guard's own list (coordinator's). model_audit and status had no test naming the effort variables until review r1 F2: reverting those hunks passed every suite.

**Why:** a fence list repeated in several modules goes stale silently; the review caught the untested two.
**How to apply:** when adding a name to a fence, grep the old name across tools/ and tests/ and test each site; mutate each by cp+restore. A re-review brief is ~20 KB to pass verbatim; `fabric-review next` needs a pinned `range: base..head` (not HEAD). Post r1 with bare `fabric-pr post-review N < file` (no chaining), then `fabric-review save N 1 < file`. `fabric-jobs done <id> owner/repo#N` is the close for a merged PR. Related: [[post-review-needs-a-file-the-owner-can-run]].

*References: post-review-needs-a-file-the-owner-can-run*

*Observed 2026-11-10 (python-dev)*
