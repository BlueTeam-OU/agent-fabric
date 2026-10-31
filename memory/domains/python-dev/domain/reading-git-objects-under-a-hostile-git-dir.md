---
role: "python-dev"
class: domain
topic: "reading-git-objects-under-a-hostile-git-dir"
description: "reading signed content from a repo whose .git the agent owns - replace refs, loose objects, grafts, commit-graph, what a mutation test must pin"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-18"
origin:
  - agent: "python-dev-01"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - fae86c7da34a9631
---

## reading signed content from a repo whose .git the agent owns - replace refs, loose objects, grafts, commit-graph, what a mutation test must pin

A signature on a commit proves nothing about bytes read through git's object layer when the reader's adversary owns `.git`. Found by the blind review of addenda.load (j122, branch holder-addenda-read, 2750051a, 5ad560df):

- `git cat-file` honours refs/replace and does not re-hash loose objects: read with `--no-replace-objects` AND hash every object you rely on (the verified commit, each tree down to the directory, each blob) against the oid that names it. Run `verify-commit` with `--no-replace-objects` too, or a replace ref stands a signed commit in for an unsigned one.
- `.git/info/grafts` rewrites parents and `--no-replace-objects` does not turn it off; core.py's `_run` scrubs GIT_GRAFT_FILE from every git env, so refuse when the file exists. `-c core.commitGraph=false` for merge-base/log.
- "No such directory" is a claim the adversary can make (reset, unsigned deletion): check the HEAD-descends-from-base rule before the absence branch, and require a removal commit to be signed by the same writer.
- A check that no test can fail (defence in depth) is a surviving mutation: drop it, or build the attack that needs it. Only a concurrent process swapping a loose object between signature check and hash check stays open; say so in the docstring.

**Why:** ADR-060 section 6 calls the signer check a fence, but the owner's threat model line "must not render text the parent did not sign" was met only after these.
**How to apply:** any reader of agent-owned git state for a trust decision; plant one mutation per flag above.

*Observed 2026-10-17 (python-dev)*
