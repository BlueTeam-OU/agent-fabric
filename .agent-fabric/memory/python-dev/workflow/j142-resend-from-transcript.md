---
role: "python-dev"
class: workflow
topic: "j142-resend-from-transcript"
description: "j142 — resending a lost GZCoord message: rebuild it from the earlier session's transcript and verify by the sha in gzcoord-sent.jsonl"
tier: 1
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "python-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - 8d8156d2edda577d
---

## j142 — resending a lost GZCoord message: rebuild it from the earlier session's transcript and verify by the sha in gzcoord-sent.jsonl

A message file swept with its scratchpad can be rebuilt: gzcoord-sent.jsonl holds the MESSAGE-ID and sha256 of what was sent; the old session's transcript (~/.claude/projects/<dir>/<session>.jsonl) has the gzcoord-compose stdout (toolUseResult.stdout) and the python fill-in heredoc. Re-run the fill on the skeleton, compare sha256, then `gzcoord-send` (same MESSAGE-ID, `--dry-run` first). Done in j142: matched byte for byte, relay seq 1075334.

**Why:** the sha proves the resend is the original, not a paraphrase.
**How to apply:** do not rewrite stale bodies; add a short REPLY saying what is superseded. Any status line naming a PR needs its counts from `fabric-pr gate` (Stop hook pr-counts.py), merged PRs included.

*Observed 2026-11-13 (python-dev)*
